(() => {
  'use strict';

  const button = document.getElementById('voice-note-button');
  const field = document.getElementById('job-note-content');
  const status = document.getElementById('voice-note-status');
  if (!button || !field || !status) return;

  const BrowserSpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!BrowserSpeechRecognition) {
    status.textContent = 'Tento prehliadač nepodporuje diktovanie v aplikácii. Poznámku môžete napísať.';
    return;
  }
  if (!window.isSecureContext) {
    status.textContent = 'Diktovanie vyžaduje HTTPS alebo lokálny pracovný priestor.';
    return;
  }

  const recognition = new BrowserSpeechRecognition();
  recognition.lang = 'sk-SK';
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  let listening = false;
  let starting = false;
  let received = false;
  let failed = false;
  let handledResults = new Set();

  button.hidden = false;
  recognition.onstart = () => {
    starting = false;
    listening = true;
    button.disabled = false;
    button.textContent = 'Zastaviť diktovanie';
    button.setAttribute('aria-pressed', 'true');
    status.textContent = 'Počúvam. Povedzte krátku poznámku.';
  };

  recognition.onresult = (event) => {
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      if (!result.isFinal || handledResults.has(index)) continue;
      handledResults.add(index);
      const transcript = (result[0]?.transcript || '').trim();
      if (!transcript) continue;
      field.value = field.value.trimEnd()
        ? field.value.trimEnd() + '\n' + transcript
        : transcript;
      received = true;
      status.textContent = 'Prepis je v poznámke. Skontrolujte ho pred uložením.';
    }
  };

  recognition.onerror = (event) => {
    failed = true;
    const messages = {
      'not-allowed': 'Mikrofón nie je povolený. Povoľte ho v prehliadači alebo poznámku napíšte.',
      'service-not-allowed': 'Prehliadač nepovolil hlasový prepis. Poznámku môžete napísať.',
      'audio-capture': 'Mikrofón sa nepodarilo použiť. Skontrolujte pripojenie mikrofónu.',
      'no-speech': 'Nepodarilo sa zachytiť reč. Skúste hovoriť bližšie k mikrofónu.',
      'network': 'Hlasový prepis teraz nemá spojenie. Poznámku môžete napísať.',
      'language-not-supported': 'Slovenčina nie je v tomto prehliadači podporovaná. Poznámku môžete napísať.'
    };
    status.textContent = messages[event.error] || 'Prepis sa nepodaril. Poznámku môžete napísať.';
  };

  recognition.onend = () => {
    starting = false;
    listening = false;
    button.disabled = false;
    button.textContent = '🎙 Diktovať po slovensky';
    button.setAttribute('aria-pressed', 'false');
    if (!failed) {
      status.textContent = received
        ? 'Prepis je v poznámke. Skontrolujte ho a potom uložte.'
        : 'Prepis sa nezískal. Skúste diktovať znovu alebo poznámku napíšte.';
    }
  };

  button.addEventListener('click', () => {
    if (listening) {
      recognition.stop();
      status.textContent = 'Zastavujem diktovanie…';
      return;
    }
    if (starting) return;
    starting = true;
    received = false;
    failed = false;
    handledResults = new Set();
    button.disabled = true;
    status.textContent = 'Žiadam o prístup k mikrofónu…';
    try {
      recognition.start();
    } catch (error) {
      starting = false;
      button.disabled = false;
      status.textContent = 'Diktovanie sa nepodarilo spustiť. Skúste znova alebo poznámku napíšte.';
    }
  });

  field.form?.addEventListener('submit', () => {
    if (listening || starting) recognition.abort();
  });
})();
