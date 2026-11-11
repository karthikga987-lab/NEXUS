
import { useState } from "react";
import { Bot, Send, User, Sparkles } from "lucide-react";
import "./AIAssistant.css";

export default function AIAssistant({ company }) {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: `Hello! I'm your NEXUS AI Assistant. I can help you explore product intelligence for ${company?.name || "your company"}. What would you like to investigate?`,
    },
  ]);

  function handleSend(e) {
    e.preventDefault();

    const text = message.trim();
    if (!text) return;

    setMessages((previous) => [
      ...previous,
      { role: "user", text },
      {
        role: "assistant",
        text: "Thanks for your question! AI analysis will be available when the NEXUS intelligence service is integrated.",
      },
    ]);

    setMessage("");
  }

  return (
    <div className="ai-assistant">
      <div className="ai-welcome">
        <div className="ai-icon">
          <Sparkles size={25} />
        </div>
        <div>
          <h2>NEXUS Intelligence Assistant</h2>
          <p>
            Ask questions about products, competitors, customer feedback,
            and market developments.
          </p>
        </div>
      </div>

      <div className="ai-chat-window">
        {messages.map((item, index) => (
          <div
            key={index}
            className={`ai-message ${item.role}`}
          >
            <div className="ai-avatar">
              {item.role === "assistant" ? (
                <Bot size={19} />
              ) : (
                <User size={19} />
              )}
            </div>

            <div className="ai-message-content">
              <span>
                {item.role === "assistant" ? "NEXUS AI" : "You"}
              </span>
              <p>{item.text}</p>
            </div>
          </div>
        ))}
      </div>

      <form className="ai-input-area" onSubmit={handleSend}>
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Ask NEXUS anything..."
        />

        <button type="submit" disabled={!message.trim()}>
          <Send size={18} />
          Send
        </button>
      </form>

      <p className="ai-disclaimer">
        AI responses are currently in demonstration mode.
      </p>
    </div>
  );
}
