// src/stores/slices/chunkedMessagesSlice.ts

import { StateCreator } from 'zustand';
import { StoreState } from '..';

type ChunkFeedback = {
  rating?: 'positive' | 'negative';
  comment?: string;
  selectedText?: string; 
  timestamp?: number;   
};

// Store the complete text and all feedback data
type chunkedMessagesState = {
  // Complete responses
  responses: {
    stream1: string;
    stream2: string;
  };
  
  // Track chunking
  chunks: {
    stream1: string[];
    stream2: string[];
  };
  
  // Enhanced feedback data per chunk
  feedback: {
    stream1: ChunkFeedback[];
    stream2: ChunkFeedback[];
  };
  
  // Current visible chunk index for EACH stream
  currentChunkIndices: {
    stream1: number;
    stream2: number;
  };
  
  // Track completion status
  isComplete: boolean;
  
  // Is testing mode active
  isChunked: boolean;
  
  // Currently selected text for feedback
  selectedText: string;
  
  // Currently active feedback stream and index
  activeFeedback: {
    streamId: 'stream1' | 'stream2' | null;
    chunkIndex: number | null;
  };
};

// Define actions for the slice
type chunkedMessagesActions = {
  startFeedbackSession: () => void;
  updateStreamContent: (streamId: 'stream1' | 'stream2', content: string) => void;
  completeStreams: () => void;
  createChunks: (chunkSize?: number) => void;
  recordFeedback: (
    streamId: 'stream1' | 'stream2', 
    chunkIndex: number, 
    feedback: ChunkFeedback
  ) => void;
  showNextChunk: () => void;
  showNextChunkForStream: (streamId: 'stream1' | 'stream2') => void;
  setSelectedText: (text: string, streamId: 'stream1' | 'stream2', chunkIndex: number) => void;
  clearSelectedText: () => void;
  resetFeedbackSession: () => void;
  resetEverything: () => void;
  
  // New methods for UI interaction
  getFeedbackForChunk: (streamId: 'stream1' | 'stream2', chunkIndex: number) => ChunkFeedback | undefined;
  getSelectedTextFeedback: () => { text: string; streamId: 'stream1' | 'stream2' | null; chunkIndex: number | null; };
  
  // New method to get decorated chunk based on current visibility
  getDecoratedChunk: (streamId: 'stream1' | 'stream2', chunkIndex: number) => string;
};

export type chunkedMessagesStore = {
  chunkedMessages: chunkedMessagesState;
} & chunkedMessagesActions;

// Initial state
const INITIAL_STATE: chunkedMessagesState = {
  responses: {
    stream1: '',
    stream2: '',
  },
  chunks: {
    stream1: [],
    stream2: [],
  },
  feedback: {
    stream1: [],
    stream2: [],
  },
  currentChunkIndices: {
    stream1: 0,
    stream2: 0,
  },
  isComplete: false,
  isChunked: false,
  selectedText: '',
  activeFeedback: {
    streamId: null,
    chunkIndex: null,
  }
};

export const createchunkedMessagesSlice: StateCreator<StoreState, [], [], chunkedMessagesStore> = (set, get) => ({
  chunkedMessages: INITIAL_STATE,
  
  startFeedbackSession: () => {
    set((state) => {
      // Instead of using INITIAL_STATE which resets everything,
      // preserve the existing chunks and responses but reset the feedback
      return {
        chunkedMessages: {
          ...state.chunkedMessages,
          isChunked: true,
          currentChunkIndices: {
            stream1: 0,
            stream2: 0
          },
          // Create fresh feedback arrays based on current chunk counts
          feedback: {
            stream1: Array(state.chunkedMessages?.chunks?.stream1?.length || 0)
              .fill(null)
              .map(() => ({})),
            stream2: Array(state.chunkedMessages?.chunks?.stream2?.length || 0)
              .fill(null)
              .map(() => ({}))
          }
        }
      };
    });
  },
  
  updateStreamContent: (streamId, content) => {
    set((state) => ({
      chunkedMessages: {
        ...state.chunkedMessages,
        responses: {
          ...state.chunkedMessages.responses,
          [streamId]: content,
        }
      }
    }));
  },
  
  completeStreams: () => {
    set((state) => ({
      chunkedMessages: {
        ...state.chunkedMessages,
        isComplete: true,
        currentChunkIndices: {
          stream1: 0,
          stream2: 0
        }
      }
    }));
    
    // Once complete, automatically create chunks
    get().createChunks();
  },
  
  createChunks: (maxChunkSize = 800) => {
    set((state) => {
      const { stream1, stream2 } = state.chunkedMessages.responses;
      
      // Simple function to chunk text into segments (without decorations)
      const createTextChunks = (text: string): string[] => {
        const chunks: string[] = [];
        
        // If text is empty, return empty array
        if (!text) return chunks;
        
        // Split text into chunks of maxChunkSize characters (no decorations added here)
        for (let i = 0; i < text.length; i += maxChunkSize) {
          const chunk = text.substring(i, Math.min(i + maxChunkSize, text.length));
          chunks.push(chunk);
        }
        
        return chunks;
      };
      
      // Create chunks for each stream
      const stream1Chunks = createTextChunks(stream1);
      const stream2Chunks = createTextChunks(stream2);
      
      // Create empty feedback slots for each chunk
      const createEmptyFeedback = (count: number) => {
        return Array(count).fill(null).map(() => ({}));
      };
      
      return {
        chunkedMessages: {
          ...state.chunkedMessages,
          chunks: {
            stream1: stream1Chunks,
            stream2: stream2Chunks,
          },
          feedback: {
            stream1: createEmptyFeedback(stream1Chunks.length),
            stream2: createEmptyFeedback(stream2Chunks.length),
          }
        }
      };
    });
  },
  
  recordFeedback: (streamId, chunkIndex, chunkFeedback) => {
    set((state) => {
      // Make sure feedback arrays exist
      const streamFeedback = state.chunkedMessages.feedback[streamId] || [];
      
      // Create a new array with the updated feedback at the specified index
      const updatedFeedback = [...streamFeedback];
      
      // Add timestamp to the feedback
      const feedbackWithTimestamp = {
        ...chunkFeedback,
        timestamp: Date.now()
      };
      
      // Update the feedback at the specified index
      updatedFeedback[chunkIndex] = feedbackWithTimestamp;
      
      return {
        chunkedMessages: {
          ...state.chunkedMessages,
          feedback: {
            ...state.chunkedMessages.feedback,
            [streamId]: updatedFeedback
          },
          // Clear selected text and active feedback after recording
          selectedText: '',
          activeFeedback: {
            streamId: null,
            chunkIndex: null
          }
        }
      };
    });
  },
  
  // Keep the original function to advance both streams simultaneously if needed
  showNextChunk: () => {
    set((state) => {
      const nextIndex1 = state.chunkedMessages.currentChunkIndices.stream1 + 1;
      const nextIndex2 = state.chunkedMessages.currentChunkIndices.stream2 + 1;
      const maxIndex1 = state.chunkedMessages.chunks.stream1.length - 1;
      const maxIndex2 = state.chunkedMessages.chunks.stream2.length - 1;
      
      return {
        chunkedMessages: {
          ...state.chunkedMessages,
          currentChunkIndices: {
            stream1: Math.min(nextIndex1, maxIndex1),
            stream2: Math.min(nextIndex2, maxIndex2)
          }
        }
      };
    });
  },
  
  // New function to advance only one stream
  showNextChunkForStream: (streamId: 'stream1' | 'stream2') => {
    set((state) => {
      // Ensure chunkedMessages exists
      if (!state.chunkedMessages) {
        return { chunkedMessages: INITIAL_STATE };
      }
      
      // Ensure currentChunkIndices exists with defaults
      const currentIndices = state.chunkedMessages.currentChunkIndices || { stream1: 0, stream2: 0 };
      
      // Ensure chunks exists with defaults
      const chunks = state.chunkedMessages.chunks || { stream1: [], stream2: [] };
      const streamChunks = chunks[streamId] || [];
      
      // Safely get current index with fallback to 0
      const currentIndex = currentIndices[streamId] ?? 0;
      
      // Calculate next index
      const nextIndex = currentIndex + 1;
      const maxIndex = Math.max(0, streamChunks.length - 1);
      
      return {
        chunkedMessages: {
          ...state.chunkedMessages,
          // Ensure we have the new structure in state
          chunks: chunks,
          currentChunkIndices: {
            ...currentIndices,
            [streamId]: Math.min(nextIndex, maxIndex)
          }
        }
      };
    });
  },
  
  resetFeedbackSession: () => {
    set({
      chunkedMessages: INITIAL_STATE
    });
  },

  resetEverything: () => {
    set((state) => {
      // Keep existing responses and chunks
      const existingResponses = state.chunkedMessages?.responses || INITIAL_STATE.responses;
      const existingChunks = state.chunkedMessages?.chunks || INITIAL_STATE.chunks;
      
      // Create fresh empty feedback arrays based on current chunk counts
      const createEmptyFeedback = (count: number) => {
        return Array(count).fill(null).map(() => ({}));
      };
      
      return {
        chunkedMessages: {
          // Keep these parts
          responses: existingResponses,
          chunks: existingChunks,
          
          // Reset these parts
          currentChunkIndices: {
            stream1: 0,
            stream2: 0
          },
          feedback: {
            stream1: createEmptyFeedback(existingChunks.stream1.length),
            stream2: createEmptyFeedback(existingChunks.stream2.length),
          },
          
          // Keep this true so we don't auto-start a feedback session again
          isChunked: true,
          isComplete: true
        }
      };
    });
  },

  setSelectedText: (text, streamId, chunkIndex) => {
    set((state) => ({
      chunkedMessages: {
        ...state.chunkedMessages,
        selectedText: text,
        activeFeedback: {
          streamId,
          chunkIndex
        }
      }
    }));
  },

  clearSelectedText: () => {
    set((state) => ({
      chunkedMessages: {
        ...state.chunkedMessages,
        selectedText: '',
        activeFeedback: {
          streamId: null,
          chunkIndex: null
        }
      }
    }));
  },

  getFeedbackForChunk: (streamId, chunkIndex) => {
    const { feedback } = get().chunkedMessages;
    const streamFeedback = feedback[streamId] || [];
    return streamFeedback[chunkIndex];
  },
  
  // Helper method to get currently selected text information
  getSelectedTextFeedback: () => {
    const { selectedText, activeFeedback } = get().chunkedMessages;
    return {
      text: selectedText,
      streamId: activeFeedback.streamId,
      chunkIndex: activeFeedback.chunkIndex
    };
  },
  
  // New method to get a chunk with decorations only if it's the currently visible one
  getDecoratedChunk: (streamId, chunkIndex) => {
    const state = get().chunkedMessages;
    const chunks = state.chunks[streamId] || [];
    const currentIndex = state.currentChunkIndices[streamId];
    
    // If the requested chunk doesn't exist, return empty string
    if (!chunks[chunkIndex]) return '';
    
    // Get the raw chunk content
    const chunk = chunks[chunkIndex];
    
    // Only add decorations if this is the currently visible chunk
    if (chunkIndex === currentIndex) {
      // Using Unicode emoji for right arrow (prefix) and left arrow (suffix)
      const prefix = '➡️ ';
      const suffix = ' ⬅️';
      return prefix + chunk + suffix;
    }
    
    // Otherwise return the chunk without decorations
    return chunk;
  }
});