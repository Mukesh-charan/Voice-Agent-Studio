(function() {
  // Find this script tag to extract data attributes
  const currentScript = document.currentScript || (function() {
    const scripts = document.getElementsByTagName('script');
    return scripts[scripts.length - 1];
  })();

  const agentId = currentScript.getAttribute('data-agent-id');
  const hostUrl = currentScript.src.split('/widget.js')[0] || '';

  if (!agentId) {
    console.error('Voice Agent Studio Widget: Missing data-agent-id attribute on script tag.');
    return;
  }

  // Inject CSS
  const style = document.createElement('style');
  style.innerHTML = `
    .vas-widget-btn {
      position: fixed;
      bottom: 24px;
      right: 24px;
      width: 60px;
      height: 60px;
      border-radius: 30px;
      background: linear-gradient(135deg, #6366f1, #a855f7);
      color: white;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 28px;
      z-index: 999999;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
      border: none;
      outline: none;
    }
    .vas-widget-btn:hover {
      transform: scale(1.05);
      box-shadow: 0 6px 16px rgba(0,0,0,0.2);
    }
    .vas-widget-window {
      position: fixed;
      bottom: 100px;
      right: 24px;
      width: 360px;
      height: 500px;
      max-height: calc(100vh - 120px);
      background: #ffffff;
      border-radius: 16px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.12);
      display: flex;
      flex-direction: column;
      z-index: 999999;
      overflow: hidden;
      opacity: 0;
      transform: translateY(20px) scale(0.95);
      pointer-events: none;
      transition: opacity 0.3s ease, transform 0.3s ease;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      border: 1px solid rgba(0,0,0,0.08);
    }
    .vas-widget-window.vas-open {
      opacity: 1;
      transform: translateY(0) scale(1);
      pointer-events: auto;
    }
    .vas-widget-header {
      background: linear-gradient(135deg, #6366f1, #a855f7);
      color: white;
      padding: 16px;
      font-weight: 600;
      font-size: 16px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .vas-widget-close {
      cursor: pointer;
      background: none;
      border: none;
      color: white;
      font-size: 20px;
      line-height: 1;
      opacity: 0.8;
      transition: opacity 0.2s;
    }
    .vas-widget-close:hover {
      opacity: 1;
    }
    .vas-widget-body {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: #f9fafb;
    }
    .vas-msg {
      max-width: 85%;
      padding: 10px 14px;
      border-radius: 14px;
      font-size: 14px;
      line-height: 1.4;
      word-wrap: break-word;
    }
    .vas-msg-user {
      align-self: flex-end;
      background: #6366f1;
      color: white;
      border-bottom-right-radius: 4px;
    }
    .vas-msg-agent {
      align-self: flex-start;
      background: white;
      color: #111827;
      border: 1px solid #e5e7eb;
      border-bottom-left-radius: 4px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    }
    .vas-widget-footer {
      padding: 12px;
      background: white;
      border-top: 1px solid #f3f4f6;
      display: flex;
      gap: 8px;
    }
    .vas-widget-input {
      flex: 1;
      border: 1px solid #e5e7eb;
      border-radius: 20px;
      padding: 8px 16px;
      font-size: 14px;
      outline: none;
      transition: border-color 0.2s;
    }
    .vas-widget-input:focus {
      border-color: #6366f1;
    }
    .vas-widget-send {
      background: #6366f1;
      color: white;
      border: none;
      border-radius: 20px;
      padding: 0 16px;
      cursor: pointer;
      font-weight: 500;
      transition: background 0.2s;
    }
    .vas-widget-send:hover {
      background: #4f46e5;
    }
    .vas-widget-send:disabled {
      background: #9ca3af;
      cursor: not-allowed;
    }
    .vas-typing {
      font-size: 12px;
      color: #6b7280;
      align-self: flex-start;
      margin-left: 8px;
      display: none;
    }
  `;
  document.head.appendChild(style);

  // Create UI
  const btn = document.createElement('button');
  btn.className = 'vas-widget-btn';
  btn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width: 28px; height: 28px;"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>';
  document.body.appendChild(btn);

  const win = document.createElement('div');
  win.className = 'vas-widget-window';
  win.innerHTML = `
    <div class="vas-widget-header">
      <span>AI Assistant</span>
      <button class="vas-widget-close">&times;</button>
    </div>
    <div class="vas-widget-body" id="vas-body"></div>
    <div class="vas-typing" id="vas-typing">Typing...</div>
    <form class="vas-widget-footer" id="vas-form">
      <input type="text" class="vas-widget-input" id="vas-input" placeholder="Type a message..." autocomplete="off" />
      <button type="submit" class="vas-widget-send" id="vas-send">Send</button>
    </form>
  `;
  document.body.appendChild(win);

  let isOpen = false;
  btn.addEventListener('click', () => {
    isOpen = !isOpen;
    if (isOpen) {
      win.classList.add('vas-open');
      btn.style.display = 'none';
      setTimeout(() => document.getElementById('vas-input').focus(), 300);
    }
  });

  win.querySelector('.vas-widget-close').addEventListener('click', () => {
    isOpen = false;
    win.classList.remove('vas-open');
    btn.style.display = 'flex';
  });

  const bodyEl = document.getElementById('vas-body');
  const inputEl = document.getElementById('vas-input');
  const formEl = document.getElementById('vas-form');
  const sendBtn = document.getElementById('vas-send');
  const typingEl = document.getElementById('vas-typing');

  let messages = [];

  function addMessage(role, content) {
    messages.push({ role, content });
    const div = document.createElement('div');
    div.className = 'vas-msg ' + (role === 'user' ? 'vas-msg-user' : 'vas-msg-agent');
    div.textContent = content;
    bodyEl.appendChild(div);
    bodyEl.scrollTop = bodyEl.scrollHeight;
  }

  const callUid = 'widget-' + Math.random().toString(36).substring(2, 10) + '-' + Date.now();

  formEl.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = inputEl.value.trim();
    if (!text) return;

    inputEl.value = '';
    addMessage('user', text);
    
    sendBtn.disabled = true;
    inputEl.disabled = true;
    typingEl.style.display = 'block';
    bodyEl.scrollTop = bodyEl.scrollHeight;

    try {
      const res = await fetch(hostUrl + '/api/public/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          agent_id: parseInt(agentId),
          call_uid: callUid,
          messages: messages
        })
      });
      
      const data = await res.json();
      if (res.ok && data.reply) {
        addMessage('assistant', data.reply);
      } else {
        addMessage('assistant', 'Sorry, I am having trouble connecting right now.');
      }
    } catch (err) {
      addMessage('assistant', 'Sorry, there was a network error.');
    } finally {
      sendBtn.disabled = false;
      inputEl.disabled = false;
      typingEl.style.display = 'none';
      inputEl.focus();
    }
  });

})();
