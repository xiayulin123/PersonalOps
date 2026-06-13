export type OAuthCallbackPayload = {
  provider: string;
  code?: string | null;
  state?: string | null;
  error?: string | null;
  error_description?: string | null;
};

const MESSAGE_TYPE = "personalops-oauth-callback";

export function listenOAuthPopup(
  expectedProvider: "microsoft" | "google",
  onPayload: (payload: OAuthCallbackPayload) => void
): () => void {
  const handler = (event: MessageEvent) => {
    const data = event.data;
    if (!data || data.type !== MESSAGE_TYPE) return;
    const payload = data.payload as OAuthCallbackPayload;
    if (payload.provider !== expectedProvider) return;
    onPayload(payload);
  };
  window.addEventListener("message", handler);
  return () => window.removeEventListener("message", handler);
}
