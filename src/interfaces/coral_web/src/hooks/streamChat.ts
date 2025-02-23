import { EventSourceMessage } from '@microsoft/fetch-event-source';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef } from 'react';

import {
  ChatResponseEvent as ChatResponse,
  CohereChatRequest,
  CohereNetworkError,
  ConversationPublic,
  FinishReason,
  StreamEnd,
  StreamEvent,
  isUnauthorizedError,
  useCohereClient,
} from '@/cohere-client';
import { useExperimentalFeatures } from '@/hooks/experimentalFeatures';

interface StreamingParams {
  onRead: (data: ChatResponse) => void;
  onHeaders: (headers: Headers) => void;
  onFinish: () => void;
  onError: (error: unknown) => void;
}

export interface StreamingChatParams extends StreamingParams {
  request: CohereChatRequest;
  headers: Record<string, string>;
}

const getUpdatedConversations =
  (conversationId: string | undefined, description: string = '') =>
  (conversations: ConversationPublic[] | undefined) => {
    return conversations?.map((c) => {
      if (c.id !== conversationId) return c;

      return {
        ...c,
        description,
        updatedAt: new Date().toISOString(),
      };
    });
  };

export const useStreamChat = () => {
  const abortControllerRef = useRef<AbortController | null>(null);
  const cohereClient = useCohereClient();
  const queryClient = useQueryClient();
  const { data: experimentalFeatures } = useExperimentalFeatures();
  
  console.log('Hello World from useStreamChat');
  
  useEffect(() => {
    console.log('Experimental features:', experimentalFeatures);
  }, [experimentalFeatures]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  const retry = (failCount: number, error: CohereNetworkError) => {
    // we allow 1 retry for 401 errors
    if (isUnauthorizedError(error)) {
      return failCount < 1;
    }
    return false;
  };

  const updateConversationHistory = (data?: StreamEnd) => {
    if (!data) return;

    queryClient.setQueryData<ConversationPublic[]>(
      ['conversations'],
      getUpdatedConversations(data?.conversation_id ?? '', data?.text)
    );
  };

  const chatMutation = useMutation<StreamEnd | undefined, CohereNetworkError, StreamingChatParams>({
    mutationFn: async (params: StreamingChatParams) => {
      try {
        queryClient.setQueryData<ConversationPublic[]>(
          ['conversations'],
          getUpdatedConversations(params.request.conversation_id ?? '', params.request.message)
        );

        abortControllerRef.current = new AbortController();

        const { request, headers, onRead, onError, onFinish } = params;

        const chatStreamParams = {
          request: {
            ...request,
            // Set humanFeedback based on experimental features
            humanFeedback: experimentalFeatures?.humanFeedback === true
          },
          headers,
          signal: abortControllerRef.current.signal,
          onMessage: (event: EventSourceMessage) => {
            try {
              if (!event.data) return;
              const data = JSON.parse(event.data);

              if (data?.event === StreamEvent.STREAM_END) {
                const streamEndData = data.data as StreamEnd;

                if (streamEndData.finish_reason !== FinishReason.COMPLETE) {
                  throw new Error(streamEndData.error || 'Stream ended unexpectedly');
                }

                if (params.request.conversation_id) {
                  queryClient.setQueryData<ConversationPublic[]>(
                    ['conversations'],
                    getUpdatedConversations(params.request.conversation_id, streamEndData.text)
                  );
                }
              }
              onRead(data);
            } catch (e) {
              const errMsg = e instanceof Error ? e.message : 'unable to parse event data';
              throw new Error(errMsg);
            }
          },
          onError: (err: unknown) => {
            onError(err);
            // Rethrow to stop the operation
            throw err;
          },
          onClose: () => {
            onFinish();
          },
        };
        console.log('Chat Parameters:', {
          humanFeedback: experimentalFeatures?.humanFeedback,
          endpoint: chatStreamParams.request.humanFeedback ? 'chat-ab-test' : 'chat-stream',
          experimentalFeatures
        });
        await cohereClient.chat({ ...chatStreamParams });
      } catch (e) {
        if (isUnauthorizedError(e)) {
          await queryClient.invalidateQueries({ queryKey: ['defaultAPIKey'] });
        }
        return Promise.reject(e);
      }
    },
    retry,
    onSuccess: updateConversationHistory,
  });

  return {
    chatMutation,
    abortController: abortControllerRef,
  };
};
