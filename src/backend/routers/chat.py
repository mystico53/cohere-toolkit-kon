from typing import Any, Generator

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from backend.chat.custom.custom import CustomChat
from backend.config.routers import RouterName
from backend.crud import agent_tool_metadata as agent_tool_metadata_crud
from backend.database_models.database import DBSessionDep
from backend.schemas.agent import Agent, AgentToolMetadata
from backend.schemas.chat import ChatResponseEvent, NonStreamedChatResponse
from backend.schemas.cohere_chat import CohereChatRequest
from backend.schemas.context import Context
from backend.services.agent import validate_agent_exists
from backend.services.chat import (
    generate_chat_response,
    generate_chat_stream,
    process_chat,
    process_message_regeneration,
)
from backend.services.context import get_context
from backend.services.request_validators import validate_deployment_header

router = APIRouter(
    prefix="/v1",
    tags=[RouterName.CHAT],
)
router.name = RouterName.CHAT


@router.post("/chat-stream", dependencies=[Depends(validate_deployment_header)])
async def chat_stream(
    chat_request: CohereChatRequest,
    session: DBSessionDep,
    ctx: Context = Depends(get_context),
) -> Generator[ChatResponseEvent, Any, None]:
    """
    Stream chat endpoint to handle user messages and return chatbot responses.
    """
    ctx.with_model(chat_request.model)
    agent_id = chat_request.agent_id
    ctx.with_agent_id(agent_id)

    (
        session,
        chat_request,
        response_message,
        should_store,
        managed_tools,
        next_message_position,
        ctx,
    ) = process_chat(session, chat_request, ctx)

    return EventSourceResponse(
        generate_chat_stream(
            session,
            CustomChat().chat(
                chat_request,
                stream=True,
                managed_tools=managed_tools,
                session=session,
                ctx=ctx,
            ),
            response_message,
            should_store=should_store,
            next_message_position=next_message_position,
            ctx=ctx,
        ),
        media_type="text/event-stream",
        headers={"Connection": "keep-alive"},
        send_timeout=300,
        ping=5,
    )


@router.post(
    "/chat-stream/regenerate", dependencies=[Depends(validate_deployment_header)]
)
async def regenerate_chat_stream(
    chat_request: CohereChatRequest,
    session: DBSessionDep,
    ctx: Context = Depends(get_context),
) -> EventSourceResponse:
    """
    Endpoint to regenerate stream chat response for the last user message.
    """
    ctx.with_model(chat_request.model)

    agent_id = chat_request.agent_id
    ctx.with_agent_id(agent_id)

    if agent_id:
        agent = validate_agent_exists(session, agent_id, ctx.get_user_id())
        ctx.with_agent(Agent.model_validate(agent))

        agent_tool_metadata = (
            agent_tool_metadata_crud.get_all_agent_tool_metadata_by_agent_id(
                session, agent_id
            )
        )
        agent_tool_metadata_schema = [
            AgentToolMetadata.model_validate(x) for x in agent_tool_metadata
        ]
        ctx.with_agent_tool_metadata(agent_tool_metadata_schema)

    (
        session,
        chat_request,
        new_response_message,
        previous_response_message_ids,
        managed_tools,
        ctx,
    ) = process_message_regeneration(session, chat_request, ctx)

    return EventSourceResponse(
        generate_chat_stream(
            session,
            CustomChat().chat(
                chat_request,
                stream=True,
                managed_tools=managed_tools,
                session=session,
                ctx=ctx,
            ),
            new_response_message,
            next_message_position=new_response_message.position,
            previous_response_message_ids=previous_response_message_ids,
            ctx=ctx,
        ),
        media_type="text/event-stream",
        headers={"Connection": "keep-alive"},
        send_timeout=300,
        ping=5,
    )


@router.post("/chat", dependencies=[Depends(validate_deployment_header)])
async def chat(
    chat_request: CohereChatRequest,
    session: DBSessionDep,
    ctx: Context = Depends(get_context),
) -> NonStreamedChatResponse:
    """
    Chat endpoint to handle user messages and return chatbot responses.
    """
    ctx.with_model(chat_request.model)
    agent_id = chat_request.agent_id
    ctx.with_agent_id(agent_id)
    user_id = ctx.get_user_id()

    if agent_id:
        agent = validate_agent_exists(session, agent_id, user_id)
        agent_schema = Agent.model_validate(agent)
        ctx.with_agent(agent_schema)
        agent_tool_metadata = (
            agent_tool_metadata_crud.get_all_agent_tool_metadata_by_agent_id(
                session, agent_id
            )
        )
        agent_tool_metadata_schema = [
            AgentToolMetadata.model_validate(x) for x in agent_tool_metadata
        ]
        ctx.with_agent_tool_metadata(agent_tool_metadata_schema)

    (
        session,
        chat_request,
        response_message,
        should_store,
        managed_tools,
        next_message_position,
        ctx,
    ) = process_chat(session, chat_request, ctx)

    response = await generate_chat_response(
        session,
        CustomChat().chat(
            chat_request,
            session=session,
            stream=False,
            managed_tools=managed_tools,
            ctx=ctx,
        ),
        response_message,
        should_store=should_store,
        next_message_position=next_message_position,
        ctx=ctx,
    )
    return response


from fastapi import APIRouter, Depends
from typing import Any, Dict

from backend.model_deployments.cohere_platform import CohereDeployment
from backend.schemas.chat import NonStreamedChatResponse
from backend.schemas.cohere_chat import CohereChatRequest
from backend.schemas.context import Context
from backend.services.context import get_context
from backend.database_models.database import DBSessionDep
from backend.services.request_validators import validate_deployment_header

router = APIRouter(
    prefix="/v1",
    tags=["experimental"],
)


@router.post("/chat-ab-test")
async def chat_ab_test(
    chat_request: CohereChatRequest,
    session: DBSessionDep,
    ctx: Context = Depends(get_context),
) -> Dict[str, Any]:
    """
    Test endpoint that makes two identical chat requests using c4ai-aya-expanse-32b model
    and returns both responses.
    """
    try:
        # Set model explicitly
        if not chat_request.model:
            chat_request.model = "c4ai-aya-expanse-32b"

        if chat_request.model:  # Type check guard
            ctx.with_model(chat_request.model)

        # Create two separate deployment instances
        deployment_a = CohereDeployment()
        deployment_b = CohereDeployment()

        # Initialize responses
        response_a = None
        response_b = None

        # Create a fresh request for the second call using the original data
        # instead of trying to deep copy the complex object
        request_data_b = {
            "message": chat_request.message,
            "chat_history": [],  # Start with empty history for the second call
            "model": chat_request.model,
            "agent_id": chat_request.agent_id
            if hasattr(chat_request, "agent_id")
            else None,
            # Add other fields as needed
        }
        chat_request_b = CohereChatRequest(**request_data_b)

        # Get a fresh context for the second call
        ctx_b = Context()
        if chat_request.model:
            ctx_b.with_model(chat_request.model)
        if hasattr(chat_request, "agent_id") and chat_request.agent_id:
            ctx_b.with_agent_id(chat_request.agent_id)

        # Make first call
        async for response in deployment_a.invoke_chat(chat_request, ctx=ctx):
            response_a = response

        # Make second call with the fresh request and context
        async for response in deployment_b.invoke_chat(chat_request_b, ctx=ctx_b):
            response_b = response

        return {
            "variant_a": response_a,
            "variant_b": response_b,
            "model": chat_request.model,
            "success": True,
        }
    except Exception as e:
        return {
            "error": str(e),
            "model": chat_request.model if chat_request.model else "unknown",
            "success": False,
        }
