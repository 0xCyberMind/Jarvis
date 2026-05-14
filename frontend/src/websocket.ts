export type MessageHandler = (message: string) => void;

export class JarvisSocket {
  private socket: WebSocket | null = null;

  connect(onMessage: MessageHandler, onStatus: (status: string) => void): void {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    this.socket = new WebSocket(`${protocol}://localhost:8000/ws`);

    this.socket.onopen = () => onStatus("Connected");
    this.socket.onclose = () => onStatus("Disconnected");
    this.socket.onerror = () => onStatus("Error");
    this.socket.onmessage = (event) => {
      const payload = JSON.parse(event.data) as { type: string; message: string };
      if (payload.type === "assistant") {
        onMessage(payload.message);
      }
    };
  }

  send(message: string): void {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      throw new Error("WebSocket is not connected");
    }
    this.socket.send(JSON.stringify({ message }));
  }
}
