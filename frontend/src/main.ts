import { OrbVisualizer } from "./orb";
import { UI } from "./ui";
import { VoiceController } from "./voice";
import { JarvisSocket } from "./websocket";

const ui = new UI();
const voice = new VoiceController();
const socket = new JarvisSocket();
const orbContainer = document.getElementById("orb");

if (!orbContainer) throw new Error("Orb container not found");
const orb = new OrbVisualizer(orbContainer);

socket.connect(
  (assistantMessage) => {
    ui.addMessage("assistant", assistantMessage);
    orb.setSpeaking(true);
    voice.speak(assistantMessage);
    setTimeout(() => orb.setSpeaking(false), 1200);
  },
  (status) => ui.setStatus(status)
);

ui.bindSend((text) => {
  try {
    ui.addMessage("user", text);
    socket.send(text);
  } catch (error) {
    ui.setStatus(error instanceof Error ? error.message : "Send failed");
  }
});

ui.bindVoice(() => {
  voice.listen(
    (text) => {
      ui.addMessage("user", text);
      socket.send(text);
    },
    (status) => ui.setStatus(status)
  );
});
