export type Sender = (text: string) => void;

export class UI {
  private messages = document.getElementById("messages") as HTMLDivElement;
  private status = document.getElementById("status") as HTMLDivElement;
  private input = document.getElementById("messageInput") as HTMLInputElement;
  private sendBtn = document.getElementById("sendBtn") as HTMLButtonElement;
  private voiceBtn = document.getElementById("voiceBtn") as HTMLButtonElement;

  bindSend(onSend: Sender): void {
    this.sendBtn.addEventListener("click", () => {
      const text = this.input.value.trim();
      if (!text) return;
      onSend(text);
      this.input.value = "";
    });

    this.input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        this.sendBtn.click();
      }
    });
  }

  bindVoice(onVoice: () => void): void {
    this.voiceBtn.addEventListener("click", onVoice);
  }

  setStatus(value: string): void {
    this.status.textContent = value;
  }

  addMessage(role: "user" | "assistant", text: string): void {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.textContent = text;
    this.messages.appendChild(div);
    this.messages.scrollTop = this.messages.scrollHeight;
  }
}
