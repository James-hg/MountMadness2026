document.addEventListener("DOMContentLoaded", () => {
    const messagesEl = document.getElementById("chatMessages");
    const inputEl = document.getElementById("chatInput");
    const sendBtn = document.getElementById("sendBtn");

    function addMessage(text, sender) {
        const msg = document.createElement("div");
        msg.classList.add("message", sender);
        msg.textContent = text;
        messagesEl.appendChild(msg);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function showTyping() {
        const msg = document.createElement("div");
        msg.classList.add("message", "typing");
        msg.id = "typingIndicator";
        msg.textContent = "AI is thinking...";
        messagesEl.appendChild(msg);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function removeTyping() {
        const el = document.getElementById("typingIndicator");
        if (el) el.remove();
    }

    async function sendMessage() {
        const text = inputEl.value.trim();
        if (!text) return;

        addMessage(text, "user");
        inputEl.value = "";
        showTyping();

        try {
            const res = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message: text }),
            });
            const data = await res.json();
            removeTyping();
            addMessage(data.reply, "ai");
        } catch {
            removeTyping();
            addMessage("Sorry, could not connect to the server.", "ai");
        }
    }

    sendBtn.addEventListener("click", sendMessage);
    inputEl.addEventListener("keydown", (e) => {
        if (e.key === "Enter") sendMessage();
    });

    // Welcome message
    addMessage("Hello! I'm your AI financial assistant. Ask me anything about your spending and income.", "ai");
});
