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

  const addProductCard = (container, product) => {
    const item = document.createElement("div");
    item.className = "chat-product-item";

    if (product.image_url) {
      const image = document.createElement("img");
      image.className = "chat-product-thumb";
      image.src = product.image_url;
      image.alt = product.name || "Sản phẩm";
      image.loading = "lazy";
      item.appendChild(image);
    } else {
      const placeholder = document.createElement("div");
      placeholder.className = "chat-product-thumb placeholder";
      placeholder.textContent = "Không có ảnh";
      item.appendChild(placeholder);
    }

    const body = document.createElement("div");
    body.className = "chat-product-body";

    const title = document.createElement("div");
    title.className = "chat-product-title";
    title.textContent = product.name || "Sản phẩm";
    body.appendChild(title);

    if (product.price_text) {
      const price = document.createElement("div");
      price.className = "chat-product-price";
      price.textContent = product.price_text;
      body.appendChild(price);
    }

    if (product.category || Number.isFinite(product.stock)) {
      const meta = document.createElement("div");
      meta.className = "chat-product-desc";
      const categoryText = product.category ? `Danh mục: ${product.category}` : "";
      const stockText = Number.isFinite(product.stock) ? `Tồn: ${product.stock}` : "";
      meta.textContent = [categoryText, stockText].filter(Boolean).join(" | ");
      if (meta.textContent) body.appendChild(meta);
    }

    if (product.short_description) {
      const desc = document.createElement("div");
      desc.className = "chat-product-desc";
      desc.textContent = product.short_description;
      body.appendChild(desc);
    }

    const actions = document.createElement("div");
    actions.className = "chat-product-actions";

    if (product.product_url) {
      const viewLink = document.createElement("a");
      viewLink.className = "btn btn-outline-secondary btn-sm";
      viewLink.href = product.product_url;
      viewLink.textContent = "Xem";
      actions.appendChild(viewLink);
    }

    if (product.add_to_cart_url) {
      const addBtn = document.createElement("button");
      addBtn.type = "button";
      addBtn.className = "btn btn-success btn-sm";
      addBtn.textContent = "Thêm vào giỏ";
      addBtn.addEventListener("click", async () => {
        addBtn.disabled = true;
        addBtn.textContent = "Đang thêm...";
        const payload = new FormData();
        payload.append("quantity", "1");
        payload.append("csrfmiddlewaretoken", csrfToken);
        try {
          const response = await fetch(product.add_to_cart_url, {
            method: "POST",
            body: payload,
            headers: { "X-Requested-With": "XMLHttpRequest" }
          });
          if (!response.ok) throw new Error("add_to_cart_failed");
          addBtn.textContent = "Đã thêm";
        } catch (_error) {
          addBtn.textContent = "Thử lại";
          addBtn.disabled = false;
        }
      });
      actions.appendChild(addBtn);
    }

    body.appendChild(actions);
    item.appendChild(body);
    container.appendChild(item);
  };

  const appendMessage = (role, text, extras = {}) => {
    const row = document.createElement("div");
    row.className = `chat-row ${role}`;

    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${role}`;
    bubble.textContent = text;

    if (role === "assistant" && Array.isArray(extras.products) && extras.products.length > 0) {
      const list = document.createElement("div");
      list.className = "chat-product-list";
      extras.products.forEach((product) => addProductCard(list, product));
      bubble.appendChild(document.createElement("br"));
      bubble.appendChild(list);
    }

    row.appendChild(bubble);
    shell.appendChild(row);
    scrollToEnd();
    return bubble;
  };

  const setSending = (sending) => {
    if (!sendBtn) return;
    sendBtn.disabled = sending;
    sendBtn.textContent = sending ? "Đang gửi..." : "Gửi";
  };

  const setModeBadge = (mode) => {
    if (!modeBadge || !mode) return;
    if (String(mode).startsWith("llm")) {
      modeBadge.className = "badge text-bg-success";
      modeBadge.textContent = "AI online";
      return;
    }
    modeBadge.className = "badge text-bg-warning text-dark";
    modeBadge.textContent = "Chế độ dự phòng";
  };

  const sendMessage = async (message) => {
    if (!config.endpoint) {
      return {
        response: "Thiếu cấu hình endpoint chat. Bạn tải lại trang và thử lại.",
        mode: "config_error"
      };
    }

    const payload = new FormData();
    payload.append("message", message);
    payload.append("csrfmiddlewaretoken", csrfToken);

    let response;
    try {
      response = await fetch(config.endpoint, {
        method: "POST",
        body: payload,
        headers: { "X-Requested-With": "XMLHttpRequest" }
      });
    } catch (_error) {
      return {
        response: "Không kết nối được tới máy chủ. Bạn thử tải lại trang.",
        mode: "network_error"
      };
    }

    if (response.redirected || response.status === 401 || response.status === 403) {
      return {
        response: "Phiên đăng nhập đã hết hạn. Bạn đăng nhập lại rồi thử tiếp.",
        mode: "auth_error"
      };
    }

    let data = {};
    try {
      data = await response.json();
    } catch (_error) {
      data = { response: "Hệ thống đang bận, bạn thử lại sau ít giây." };
    }

    if (!response.ok) {
      return {
        response: data.response || "Không gửi được tin nhắn. Bạn thử lại.",
        mode: data.mode || "error"
      };
    }

    return {
      response: data.response || "Mình đã nhận tin nhắn của bạn.",
      mode: data.mode || "unknown",
      products: Array.isArray(data.products) ? data.products : []
    };
  };

  const submitChat = async () => {
    const message = input.value.trim();
    if (!message) return;

    appendMessage("user", message);
    input.value = "";
    input.focus();

    const pending = appendMessage("assistant", "Mình đang phân tích yêu cầu...");
    setSending(true);

    try {
      const result = await sendMessage(message);
      pending.textContent = "";
      pending.textContent = result.response;
      if (Array.isArray(result.products) && result.products.length > 0) {
        const list = document.createElement("div");
        list.className = "chat-product-list";
        result.products.forEach((product) => addProductCard(list, product));
        pending.appendChild(document.createElement("br"));
        pending.appendChild(list);
      }
      setModeBadge(result.mode);
    } catch (_error) {
      pending.textContent = "Có lỗi bất ngờ khi xử lý tin nhắn. Bạn thử lại.";
      setModeBadge("error");
    } finally {
      setSending(false);
    }
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
    appendMessage("assistant", "Lịch sử chat đã được xóa. Bạn muốn mình hỗ trợ gì?");
  });

  scrollToEnd();
})();
