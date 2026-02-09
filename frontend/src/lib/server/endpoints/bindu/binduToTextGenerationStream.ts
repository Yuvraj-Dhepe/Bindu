/**
 * Bindu Response to TextGenerationStream Converter
 * Transforms Bindu A2A protocol responses into HuggingFace TextGenerationStreamOutput format
 */

import type { TextGenerationStreamOutput } from "@huggingface/inference";
import type {
	BinduJsonRpcResponse,
	BinduStreamEvent,
	Task,
	Artifact,
} from "./types";

/**
 * Extract text content from a task's artifacts
 */
function extractTextFromArtifacts(artifacts?: Artifact[]): string {
	if (!artifacts || artifacts.length === 0) return "";

	const textParts: string[] = [];
	for (const artifact of artifacts) {
		if (artifact.kind === "text" && artifact.text) {
			textParts.push(artifact.text);
		}
	}
	return textParts.join("");
}

/**
 * Convert a non-streaming Bindu JSON-RPC response to TextGenerationStreamOutput
 */
export async function* binduToTextGenerationStream(
	response: BinduJsonRpcResponse
): AsyncGenerator<TextGenerationStreamOutput, void, void> {
	if (response.error) {
		throw new Error(`Bindu error ${response.error.code}: ${response.error.message}`);
	}

	const task = response.result?.task;
	if (!task) {
		throw new Error("No task in Bindu response");
	}

	const text = extractTextFromArtifacts(task.artifacts);

	// Emit as final answer
	yield {
		token: {
			id: 0,
			text,
			logprob: 0,
			special: true,
		},
		generated_text: text,
		details: null,
	};
}

/**
 * Convert a streaming Bindu response (SSE events) to TextGenerationStreamOutput
 * This handles the Server-Sent Events from message/stream endpoint
 */
export async function* binduStreamToTextGenerationStream(
	reader: ReadableStreamDefaultReader<Uint8Array>,
	decoder: TextDecoder = new TextDecoder()
): AsyncGenerator<TextGenerationStreamOutput, void, void> {
	let tokenId = 0;
	let generatedText = "";
	let buffer = "";

	try {
		while (true) {
			const { done, value } = await reader.read();
			if (done) break;

			buffer += decoder.decode(value, { stream: true });
			const lines = buffer.split("\n");
			buffer = lines.pop() || "";

			for (const line of lines) {
				const trimmed = line.trim();
				if (!trimmed || trimmed.startsWith(":")) continue;

				if (trimmed.startsWith("data:")) {
					const jsonStr = trimmed.slice(5).trim();
					if (!jsonStr || jsonStr === "[DONE]") continue;

					try {
						const event: BinduStreamEvent = JSON.parse(jsonStr);
						const output = processStreamEvent(event, tokenId, generatedText);
						if (output) {
							tokenId = output.nextTokenId;
							generatedText = output.generatedText;
							yield output.output;
						}
					} catch {
						// Skip malformed JSON chunks
					}
				}
			}
		}

		// Process any remaining buffer
		if (buffer.trim()) {
			const trimmed = buffer.trim();
			if (trimmed.startsWith("data:")) {
				const jsonStr = trimmed.slice(5).trim();
				if (jsonStr && jsonStr !== "[DONE]") {
					try {
						const event: BinduStreamEvent = JSON.parse(jsonStr);
						const output = processStreamEvent(event, tokenId, generatedText);
						if (output) {
							yield output.output;
						}
					} catch {
						// Skip malformed JSON
					}
				}
			}
		}
	} finally {
		reader.releaseLock();
	}
}

interface ProcessedStreamOutput {
	output: TextGenerationStreamOutput;
	nextTokenId: number;
	generatedText: string;
}

/**
 * Process a single stream event and return the appropriate output
 */
function processStreamEvent(
	event: BinduStreamEvent,
	tokenId: number,
	currentText: string
): ProcessedStreamOutput | null {
	// Handle task status updates
	if (event.params?.status) {
		const status = event.params.status;
		const state = status.state;

		// Extract text from status message if present
		if (status.message?.parts) {
			for (const part of status.message.parts) {
				if (part.kind === "text") {
					const text = part.text;
					const newText = currentText + text;
					return {
						output: {
							token: {
								id: tokenId,
								text,
								logprob: 0,
								special: state === "completed",
							},
							generated_text: state === "completed" ? newText : null,
							details: null,
						},
						nextTokenId: tokenId + 1,
						generatedText: newText,
					};
				}
			}
		}

		// Handle completed state without message
		if (state === "completed") {
			return {
				output: {
					token: {
						id: tokenId,
						text: "",
						logprob: 0,
						special: true,
					},
					generated_text: currentText,
					details: null,
				},
				nextTokenId: tokenId + 1,
				generatedText: currentText,
			};
		}
	}

	// Handle artifact updates
	if (event.params?.artifact) {
		const artifact = event.params.artifact;
		if (artifact.kind === "text" && artifact.text) {
			const text = artifact.text;
			const newText = currentText + text;
			const isFinal = artifact.lastChunk || event.params.final;

			return {
				output: {
					token: {
						id: tokenId,
						text,
						logprob: 0,
						special: Boolean(isFinal),
					},
					generated_text: isFinal ? newText : null,
					details: null,
				},
				nextTokenId: tokenId + 1,
				generatedText: newText,
			};
		}
	}

	// Handle final result
	if (event.result?.task) {
		const task = event.result.task;
		const text = extractTextFromArtifacts(task.artifacts);

		if (text && text !== currentText) {
			const newContent = text.slice(currentText.length);
			return {
				output: {
					token: {
						id: tokenId,
						text: newContent,
						logprob: 0,
						special: true,
					},
					generated_text: text,
					details: null,
				},
				nextTokenId: tokenId + 1,
				generatedText: text,
			};
		}
	}

	return null;
}

/**
 * Helper to convert a fetch Response with SSE to TextGenerationStreamOutput
 */
export async function* binduResponseToStream(
	response: Response
): AsyncGenerator<TextGenerationStreamOutput, void, void> {
	const contentType = response.headers.get("content-type") || "";

	if (contentType.includes("text/event-stream")) {
		// Streaming response
		if (!response.body) {
			throw new Error("No response body for streaming");
		}
		const reader = response.body.getReader();
		yield* binduStreamToTextGenerationStream(reader);
	} else {
		// Non-streaming JSON response
		const json: BinduJsonRpcResponse = await response.json();
		yield* binduToTextGenerationStream(json);
	}
}
