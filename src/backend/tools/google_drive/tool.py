import os
import time
from typing import Any, Dict, List

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from backend.crud import tool_auth as tool_auth_crud
from backend.crud.agent_tool_metadata import get_all_agent_tool_metadata_by_agent_id
from backend.services.compass import Compass
from backend.services.logger import get_logger
from backend.tools.base import BaseTool
from backend.tools.utils import async_download, parallel_get_files

from .constants import (
    COMPASS_UPDATE_INTERVAL,
    DOC_FIELDS,
    GOOGLE_DRIVE_TOOL_ID,
    SEARCH_LIMIT,
    SEARCH_MIME_TYPES,
)
from .utils import (
    extract_links,
    extract_titles,
    extract_web_view_links,
    process_shortcut_files,
)

logger = get_logger()


class GoogleDrive(BaseTool):
    """
    Experimental (In development): Tool that searches Google Drive
    """

    @classmethod
    def is_available(cls) -> bool:
        vars = [
            "GOOGLE_DRIVE_CLIENT_ID",
            "GOOGLE_DRIVE_CLIENT_SECRET",
        ]
        return all(os.getenv(var) is not None for var in vars)

    def call(self, parameters: dict, **kwargs: Any) -> List[Dict[str, Any]]:
        """
        Google Drive logic
        """
        session = kwargs.get("session")
        agent_id = kwargs["agent_id"]
        index_name = "{}_{}".format(agent_id, GOOGLE_DRIVE_TOOL_ID)
        query = parameters.get("query", "")
        conditions = [
            "("
            + " or ".join(
                [f"mimeType = '{mime_type}'" for mime_type in SEARCH_MIME_TYPES]
            )
            + ")",
            "("
            + " or ".join([f"fullText contains '{word}'" for word in [query]])
            + " or "
            + " or ".join([f"name contains '{word}'" for word in [query]])
            + ")",
        ]
        auth = tool_auth_crud.get_tool_auth(
            session, GOOGLE_DRIVE_TOOL_ID, kwargs.get("user_id")
        )
        creds = Credentials(auth.encrypted_access_token.decode())

        # fetch agent tool metadata
        file_ids = []
        folder_ids = []
        agent_metadata = get_all_agent_tool_metadata_by_agent_id(
            db=session, agent_id=agent_id
        )
        for metadata in agent_metadata:
            if metadata.tool_name == GOOGLE_DRIVE_TOOL_ID:
                artifacts = metadata.artifacts
                for artifact in artifacts:
                    if artifact["type"] == "folder":
                        folder_ids.append(artifact["id"])
                    else:
                        file_ids.append(artifact["id"])

        # Condition on files if exist
        files = []
        if file_ids:
            files = parallel_get_files.perform(
                file_ids=file_ids, access_token=creds.token
            )
        else:
            # Condition on folders if exist
            if folder_ids:
                conditions.append(
                    "("
                    + " or ".join(
                        [
                            "'{}' in parents".format(folder_id)
                            for folder_id in folder_ids
                        ]
                    )
                    + ")"
                )

            q = " and ".join(conditions)
            fields = f"nextPageToken, files({DOC_FIELDS})"

            search_results = []
            try:
                service = build("drive", "v3", credentials=creds)
                search_results = (
                    service.files()
                    .list(pageSize=SEARCH_LIMIT, q=q, fields=fields)
                    .execute()
                )
            except Exception as e:
                logger.error(str(e))
                raise e

            files = search_results.get("files", [])
            if not files:
                logger.debug("No files found.")

        if not files:
            return [{"text": ""}]

        # extract links and download file contents
        files = process_shortcut_files(service, files)
        id_to_urls = extract_links(files)
        web_view_links = extract_web_view_links(files)
        titles = extract_titles(files)
        id_to_texts = async_download.perform(id_to_urls, creds.token)

        """
        Compass logic
        """
        compass = Compass()

        # idempotent create index
        compass.invoke(
            action=Compass.ValidActions.CREATE_INDEX,
            parameters={"index": index_name},
        )

        # handle creation/update of each file
        for file_id in id_to_texts:
            fetched_doc = None
            try:
                fetched_doc = compass.invoke(
                    action=Compass.ValidActions.GET_DOCUMENT,
                    parameters={"index": index_name, "file_id": file_id},
                ).result["doc"]
                url = fetched_doc["content"].get("url")
                title = fetched_doc["content"].get("title")
                last_updated = fetched_doc["content"].get("last_updated")

                should_update = False
                if last_updated is None or url is None or title is None:
                    should_update = True
                else:
                    if int(time.time()) - last_updated > COMPASS_UPDATE_INTERVAL:
                        should_update = True

                # doc update if needed
                if should_update:
                    # update
                    compass.invoke(
                        action=Compass.ValidActions.UPDATE,
                        parameters={
                            "index": index_name,
                            "file_id": file_id,
                            "file_text": id_to_texts[file_id],
                        },
                    )
                    # add context
                    compass.invoke(
                        action=Compass.ValidActions.ADD_CONTEXT,
                        parameters={
                            "index": index_name,
                            "file_id": file_id,
                            "context": {
                                "url": web_view_links[file_id],
                                "title": titles[file_id],
                                "last_updated": int(time.time()),
                            },
                        },
                    )
                    # refresh
                    compass.invoke(
                        action=Compass.ValidActions.REFRESH,
                        parameters={"index": index_name},
                    )
            except Exception:
                # create
                compass.invoke(
                    action=Compass.ValidActions.CREATE,
                    parameters={
                        "index": index_name,
                        "file_id": file_id,
                        "file_text": id_to_texts[file_id],
                    },
                )
                # add context
                compass.invoke(
                    action=Compass.ValidActions.ADD_CONTEXT,
                    parameters={
                        "index": index_name,
                        "file_id": file_id,
                        "context": {
                            "url": web_view_links[file_id],
                            "title": titles[file_id],
                            "last_updated": int(time.time()),
                        },
                    },
                )
                # refresh
                compass.invoke(
                    action=Compass.ValidActions.REFRESH,
                    parameters={"index": index_name},
                )

        # fetch documents from index
        hits = compass.invoke(
            action=Compass.ValidActions.SEARCH,
            parameters={
                "index": index_name,
                "query": query,
                "top_k": SEARCH_LIMIT,
            },
        ).result["hits"]
        chunks = [
            {
                "text": chunk["content"]["text"],
                "url": hit["content"].get("url", ""),
                "title": hit["content"].get("title", ""),
            }
            for hit in hits
            for chunk in hit["chunks"]
        ]

        return chunks
