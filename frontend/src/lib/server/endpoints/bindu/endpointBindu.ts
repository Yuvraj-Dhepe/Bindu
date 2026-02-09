/**
 * Bindu A2A Protocol Endpoint Adapter
 * Translates between chat-ui's internal format and Bindu's JSON-RPC A2A protocol
 */

import { z } from "zod";
import { config } from "$lib/server/config";
import type { Endpoint, EndpointMessage } from "../endpoints";
import { binduResponseToStream } from "./binduToTextGenerationStream";
import type { BinduMessage, Part, MessageSendParams, BinduJsonRpcRequest } from "./types";

export const endpointBinduParametersSchema = z.object({
	type: z.literal("bindu"),
	baseURL: z.string().url(),
	apiKey: z.string().optional().default(""),
	streamingSupported: z.boolean().default(true),
});

/**
 * Convert chat-ui message format to Bindu message parts
 */
function messageContentToParts(message: EndpointMessage): Part[] {
	const parts: Part[] = [];

	// Handle string content
	if (typeof message.content === "string") {
		parts.push({ kind: "text", text: message.content });
	}

	// Handle file attachments if present
	if (message.files && message.files.length > 0) {
		for (const file of message.files) {
			if (file.type === "base64") {
				parts.push({
					kind: "file",
					file: {
						name: file.name,
						mimeType: file.mime,
						bytes: file.value,
					},
				});
			}
		}
	}

	return parts;
}

/**
 * Build the complete message history for context
 */
function buildMessageHistory(
	messages: EndpointMessage[],
	contextId: string
): { lastMessage: BinduMessage; history: BinduMessage[] } {
	const history: BinduMessage[] = [];

	for (let i = 0; i < messages.length; i++) {
		const msg = messages[i];
		const binduMsg: BinduMessage = {
			role: msg.from === "assistant" ? "agent" : "user",
			parts: messageContentToParts(msg),
			kind: "message",
			messageId: crypto.randomUUID(),
			contextId,
			taskId: crypto.randomUUID(),
		};
		history.push(binduMsg);
	}

	const lastMessage = history[history.length - 1];
	return { lastMessage, history: history.slice(0, -1) };
}

/**
 * Create the Bindu endpoint handler
 */
export async function endpointBindu(
	input: z.input<typeof endpointBinduParametersSchema>
): Promise<Endpoint> {
	const { baseURL, apiKey, streamingSupported } = endpointBinduParametersSchema.parse(input);

	// Use configured API key or fall back to environment variable
	const effectiveApiKey = apiKey || config.BINDU_API_KEY || "";

	return async ({ messages, conversationId, preprompt, abortSignal }) => {
		// Filter to get actual user/assistant messages
		const conversationMessages = messages.filter(
			(m) => m.from === "user" || m.from === "assistant"
		);

		if (conversationMessages.length === 0) {
			throw new Error("No messages to send to Bindu agent");
		}

		// Use conversation ID as context ID for continuity
		const contextId = conversationId?.toString() || crypto.randomUUID();
		const taskId = crypto.randomUUID();

		// Build message with history
		const { lastMessage } = buildMessageHistory(conversationMessages, contextId);

		// Override taskId for the actual request
		lastMessage.taskId = taskId;

		// Prepare system prompt as part of configuration if present
		const systemContext = preprompt?.trim()
			? { systemPrompt: preprompt.trim() }
			: {};

		// Build JSON-RPC request params
		const params: MessageSendParams = {
			message: lastMessage,
			configuration: {
				acceptedOutputModes: ["text/plain", "application/json"],
				blocking: !streamingSupported,
				...systemContext,
			},
		};

		// Choose streaming or non-streaming method
		const method = streamingSupported ? "message/stream" : "message/send";

		const binduRequest: BinduJsonRpcRequest = {
			jsonrpc: "2.0",
			method,
			params: params as unknown as Record<string, unknown>,
			id: crypto.randomUUID(),
		};

		// Build headers
		const headers: Record<string, string> = {
			"Content-Type": "application/json",
		};

		if (effectiveApiKey) {
			headers["Authorization"] = `Bearer ${effectiveApiKey}`;
		}

		// Add streaming header if applicable
		if (streamingSupported) {
			headers["Accept"] = "text/event-stream";
		}

		// Make the request
		const response = await fetch(baseURL, {
			method: "POST",
			headers,
			body: JSON.stringify(binduRequest),
			signal: abortSignal,
		});

		if (!response.ok) {
			const errorText = await response.text().catch(() => "Unknown error");
			throw new Error(
				`Bindu request failed: ${response.status} ${response.statusText} - ${errorText}`
			);
		}

		// Convert response to text generation stream
		return binduResponseToStream(response);
	};
}
