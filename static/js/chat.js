/**
 * Chat Widget — Agentic Interface for ML Works
 * Floating chat panel accessible from every page.
 */
(function() {
    'use strict';

    const CHAT_API = '/api/chat';
    const HISTORY_API = '/api/chat/history';
    const CLEAR_API = '/api/chat/clear';

    let sessionId = localStorage.getItem('chat_session_id') || generateId();
    localStorage.setItem('chat_session_id', sessionId);

    let isOpen = localStorage.getItem('chat_open') === 'true';
    let isSending = false;

    // DOM references (set after init)
    let panel, fab, messagesEl, inputEl, sendBtn, typingEl, suggestionsEl;

    function generateId() {
        return 'sess-' + Math.random().toString(36).substr(2, 12);
    }

    function init() {
        // The HTML is injected via the chat_widget.html partial in base.html
        panel = document.getElementById('chat-panel');
        fab = document.getElementById('chat-fab');
        messagesEl = document.getElementById('chat-messages');
        inputEl = document.getElementById('chat-input');
        sendBtn = document.getElementById('chat-send-btn');
        typingEl = document.getElementById('chat-typing');
        suggestionsEl = document.getElementById('chat-suggestions');

        if (!panel || !fab) return; // Widget not present (agentic disabled)

        // Event listeners
        fab.addEventListener('click', togglePanel);
        document.getElementById('chat-close-btn').addEventListener('click', closePanel);
        sendBtn.addEventListener('click', sendMessage);
        inputEl.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // Restore state
        if (isOpen) {
            openPanel();
        }

        // Load history
        loadHistory();
    }

    function togglePanel() {
        if (panel.classList.contains('open')) {
            closePanel();
        } else {
            openPanel();
        }
    }

    function openPanel() {
        panel.classList.add('open');
        fab.classList.add('hidden');
        localStorage.setItem('chat_open', 'true');
        isOpen = true;
        inputEl.focus();
        scrollToBottom();
    }

    function closePanel() {
        panel.classList.remove('open');
        fab.classList.remove('hidden');
        localStorage.setItem('chat_open', 'false');
        isOpen = false;
    }

    function scrollToBottom() {
        setTimeout(function() {
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }, 50);
    }

    function addMessage(role, content, toolCalls) {
        var msgEl = document.createElement('div');
        msgEl.className = 'chat-message ' + role;

        // Simple markdown: bold, code, line breaks
        var html = escapeHtml(content)
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
        msgEl.innerHTML = html;

        if (role === 'assistant' && toolCalls && toolCalls.length > 0) {
            var toolInfo = document.createElement('div');
            toolInfo.className = 'tool-calls-info';
            toolInfo.textContent = '🔧 Used: ' + toolCalls.map(function(t) { return t.tool; }).join(', ');
            msgEl.appendChild(toolInfo);
        }

        messagesEl.appendChild(msgEl);
        scrollToBottom();
    }

    function showSuggestions(suggestions) {
        suggestionsEl.innerHTML = '';
        if (!suggestions || suggestions.length === 0) return;

        suggestions.forEach(function(text) {
            var chip = document.createElement('button');
            chip.className = 'chat-suggestion-chip';
            chip.textContent = text;
            chip.addEventListener('click', function() {
                inputEl.value = text;
                sendMessage();
            });
            suggestionsEl.appendChild(chip);
        });
    }

    function showTyping() {
        typingEl.classList.add('visible');
        scrollToBottom();
    }

    function hideTyping() {
        typingEl.classList.remove('visible');
    }

    function sendMessage() {
        var message = inputEl.value.trim();
        if (!message || isSending) return;

        addMessage('user', message);
        inputEl.value = '';
        suggestionsEl.innerHTML = '';
        isSending = true;
        sendBtn.disabled = true;
        showTyping();

        fetch(CHAT_API, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message, session_id: sessionId })
        })
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            hideTyping();
            isSending = false;
            sendBtn.disabled = false;

            if (data.response) {
                addMessage('assistant', data.response, data.tool_calls);
            }
            if (data.suggestions) {
                showSuggestions(data.suggestions);
            }
            if (data.session_id) {
                sessionId = data.session_id;
                localStorage.setItem('chat_session_id', sessionId);
            }
        })
        .catch(function(err) {
            hideTyping();
            isSending = false;
            sendBtn.disabled = false;
            addMessage('assistant', 'Sorry, something went wrong. Please try again.');
            console.error('Chat error:', err);
        });
    }

    function loadHistory() {
        fetch(HISTORY_API + '?session_id=' + encodeURIComponent(sessionId))
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
            if (data.history && data.history.length > 0) {
                data.history.forEach(function(msg) {
                    addMessage(msg.role, msg.content || '');
                });
            }
        })
        .catch(function() { /* ignore */ });
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
