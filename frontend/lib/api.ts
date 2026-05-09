export type Message = {
  role: "user" | "assistant";
  content: string;
};

export type Recommendation = {
  name: string;
  url: string;
  test_type: string;
};

export type ChatResponse = {
  reply: string;
  recommendations: Recommendation[];
  end_of_conversation: boolean;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Sends a chat message history to the backend agent.
 * The backend is stateless, so the full conversation history must be sent every time.
 */
export async function sendMessage(messages: Message[]): Promise<ChatResponse> {
  const response = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ messages }),
  });

  if (!response.ok) {
    let errorDetail = response.statusText;
    try {
      const errorData = await response.json();
      errorDetail = errorData.detail || errorDetail;
    } catch {
      // Ignore JSON parse errors for non-JSON responses
    }
    throw new Error(`Failed to send message: ${response.status} - ${errorDetail}`);
  }

  return response.json();
}

/**
 * Checks if the backend API is healthy and reachable.
 */
export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_URL}/health`);
    if (!response.ok) {
      return false;
    }
    const data = await response.json();
    return data.status === "ok";
  } catch (error) {
    return false;
  }
}
