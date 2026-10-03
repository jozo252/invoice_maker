const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../static/crm/job-notes.js'), 'utf8');

class Element {
  constructor() {
    this.value = '';
    this.textContent = '';
    this.hidden = true;
    this.disabled = false;
    this.attributes = {};
    this.listeners = {};
  }

  addEventListener(type, listener) {
    (this.listeners[type] ??= []).push(listener);
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  emit(type) {
    for (const listener of this.listeners[type] ?? []) listener();
  }
}

function harness({ speech = true, secure = true, draft = '' } = {}) {
  const button = new Element();
  const field = new Element();
  const status = new Element();
  let submissions = 0;
  const form = new Element();
  form.submit = form.requestSubmit = () => { submissions += 1; };
  field.value = draft;
  field.form = form;

  let recognition;
  class SpeechRecognition {
    constructor() {
      recognition = this;
      this.starts = 0;
      this.stops = 0;
      this.aborts = 0;
    }

    start() { this.starts += 1; }
    stop() { this.stops += 1; }
    abort() { this.aborts += 1; }
  }

  const elements = {
    'voice-note-button': button,
    'job-note-content': field,
    'voice-note-status': status,
  };
  const window = { isSecureContext: secure };
  if (speech) window.SpeechRecognition = SpeechRecognition;
  vm.runInNewContext(source, {
    document: { getElementById: id => elements[id] },
    window,
  }, { filename: 'job-notes.js' });

  return { button, field, status, form, recognition, submissions: () => submissions };
}

test('without SpeechRecognition the note remains writable and dictation stays hidden', () => {
  const h = harness({ speech: false, draft: 'Ručný zápis' });
  assert.equal(h.button.hidden, true);
  assert.equal(h.field.value, 'Ručný zápis');
  h.field.value += ' po obhliadke';
  assert.equal(h.field.value, 'Ručný zápis po obhliadke');
  assert.match(h.status.textContent, /Poznámku môžete napísať/);
  assert.equal(h.submissions(), 0);
});

test('final Slovak transcript is appended once and never saves the note', () => {
  const h = harness({ draft: 'Zákazník potvrdil termín' });
  assert.equal(h.button.hidden, false);
  assert.equal(h.recognition.lang, 'sk-SK');
  assert.equal(h.recognition.interimResults, false);

  h.button.emit('click');
  assert.equal(h.recognition.starts, 1);
  h.recognition.onstart();
  const interim = { resultIndex: 0, results: [{ isFinal: false, 0: { transcript: 'Montáž' } }] };
  h.recognition.onresult(interim);
  assert.equal(h.field.value, 'Zákazník potvrdil termín');

  const final = { resultIndex: 0, results: [{ isFinal: true, 0: { transcript: ' Montáž zásuviek dokončená ' } }] };
  h.recognition.onresult(final);
  h.recognition.onresult(final);
  h.recognition.onend();
  assert.equal(h.field.value, 'Zákazník potvrdil termín\nMontáž zásuviek dokončená');
  assert.match(h.status.textContent, /Skontrolujte ho a potom uložte/);
  assert.equal(h.submissions(), 0);
});

test('recognition error keeps an unfinished manual note intact', () => {
  const draft = 'Treba doplniť materiál a overiť rozmery';
  const h = harness({ draft });
  h.button.emit('click');
  h.recognition.onstart();
  h.recognition.onerror({ error: 'network' });
  h.recognition.onend();
  assert.equal(h.field.value, draft);
  assert.match(h.status.textContent, /nemá spojenie/);
  assert.equal(h.button.disabled, false);
  assert.equal(h.submissions(), 0);
});

test('second button click manually stops dictation without saving', () => {
  const h = harness({ draft: 'Pôvodná poznámka' });
  h.button.emit('click');
  h.recognition.onstart();
  assert.equal(h.button.attributes['aria-pressed'], 'true');
  h.button.emit('click');
  assert.equal(h.recognition.stops, 1);
  assert.equal(h.recognition.aborts, 0);
  assert.match(h.status.textContent, /Zastavujem diktovanie/);
  h.recognition.onend();
  assert.equal(h.button.attributes['aria-pressed'], 'false');
  assert.equal(h.field.value, 'Pôvodná poznámka');
  assert.equal(h.submissions(), 0);
});
