(() => {
  const form = document.getElementById("chatForm");
  const input = document.getElementById("chatInput");
  const shell = document.getElementById("chatShell");
  const clearBtn = document.getElementById("clearChatBtn");
  const sendBtn = document.getElementById("sendBtn");
  const modeBadge = document.getElementById("modeBadge");
  const quickReplyButtons = document.querySelectorAll(".quick-reply");
  const config = window.ChatConfig || {};
  const csrfTokenInput = document.querySelector("#chatForm input[name='csrfmiddlewaretoken']");
  const csrfToken = csrfTokenInput ? csrfTokenInput.value : "";

  if (!form || !input || !shell) return;

  const scrollToEnd = () => {
    shell.scrollTop = shell.scrollHeight;
  };

  const appendMessage = (role, text) => {
    const row = document.createElement("div");
    row.className = `chat-row ${role}`;

    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${role}`;
    bubble.textContent = text;

    row.appendChild(bubble);
    shell.appendChild(row);
    scrollToEnd();
    return bubble;
  };

  const setSending = (sending) => {
    if (!sendBtn) return;
    sendBtn.disabled = sending;
    sendBtn.textContent = sending ? "Dang gui..." : "Gui";
  };

  const setModeBadge = (mode) => {
    if (!modeBadge || !mode) return;
    if (String(mode).startsWith("llm")) {
      modeBadge.className = "badge text-bg-success";
      modeBadge.textContent = "AI online";
      return;
    }
    modeBadge.className = "badge text-bg-warning text-dark";
    modeBadge.textContent = "Fallback mode";
  };

  const sendMessage = async (message) => {
    const payload = new FormData();
    payload.append("message", message);
    payload.append("csrfmiddlewaretoken", csrfToken);

    const response = await fetch(config.endpoint, {
      method: "POST",
      body: payload,
      headers: { "X-Requested-With": "XMLHttpRequest" }
    });

    let data = {};
    try {
      data = await response.json();
    } catch (_error) {
      data = { response: "He thong dang ban, ban thu lai sau it giay." };
    }

    if (!response.ok) {
      return {
        response: data.response || "Khong gui duoc tin nhan. Ban thu lai.",
        mode: data.mode || "error"
      };
    }

    return {
      response: data.response || "Minh da nhan tin nhan cua ban.",
      mode: data.mode || "unknown"
    };
  };

  const submitChat = async () => {
    const message = input.value.trim();
    if (!message) return;

    appendMessage("user", message);
    input.value = "";
    input.focus();

    const pending = appendMessage("assistant", "Minh dang phan tich yeu cau...");
    setSending(true);

    const result = await sendMessage(message);
    pending.textContent = result.response;
    setModeBadge(result.mode);
    setSending(false);
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitChat();
  });

  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  quickReplyButtons.forEach((button) => {
    button.addEventListener("click", () => {
      input.value = button.textContent.trim();
      input.focus();
    });
  });

  clearBtn?.addEventListener("click", async () => {
    const payload = new FormData();
    payload.append("csrfmiddlewaretoken", csrfToken);
    await fetch(config.resetEndpoint, {
      method: "POST",
      body: payload,
      headers: { "X-Requested-With": "XMLHttpRequest" }
    });
    shell.innerHTML = "";
    appendMessage("assistant", "Lich su chat da duoc xoa. Ban muon minh ho tro gi?");
  });

  scrollToEnd();
})();
