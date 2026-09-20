// Voice input for the chat bar (Sprint 3, story 13). Loaded by voice.py.
//
// Adds a mic button to the left of Streamlit's chat bar. Tapping it records, and
// while recording a waveform fills the bar: thin bars that rise as you speak and
// sink to dots when you pause. Tapping again or pressing Enter stops, and the
// recording is sent back to Python, which transcribes it into the chat box.
//
// Streamlit calls the default export again whenever voice.py passes new data, and
// can mount the component afresh when the chat bar moves. One controller for the
// page therefore owns the button and any recording in progress, and re-attaches
// itself to whichever chat bar is on screen.

const BAR_SELECTOR = '.st-key-hs_chat_bar [data-testid="stChatInput"]';

const BAR_COUNT = 48;
const SAMPLE_MS = 50;        // how often a new bar enters, so ~2.4s of speech is on screen
const DOT = 0.12;            // a silent bar's height, as a share of the full height
const BUSY_TIMEOUT_MS = 90_000;

const MIME_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];

const MIC_ICON = `
<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
     stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <rect x="9" y="2.5" width="6" height="11.5" rx="3"/>
  <path d="M5.5 10.5a6.5 6.5 0 0 0 13 0"/>
  <path d="M12 17v4"/>
</svg>`;

let controller = null;

export default function ({ data, setTriggerValue }) {
    controller ??= createController();
    controller.update(data ?? {}, setTriggerValue);

    return () => controller.cancel();
}

function createController() {
    let send = () => {};
    let maxSeconds = 60;

    let host = null;
    let button = null;
    let wave = null;
    let status = null;
    let bars = [];

    let recording = false;
    let busy = false;
    let pendingId = null;
    let busyTimer = null;

    let stream = null;
    let audioContext = null;
    let analyser = null;
    let recorder = null;
    let chunks = [];
    let levels = new Array(BAR_COUNT).fill(0);
    let silenceLevel = 0.02;
    let voiced = 0;          // seconds spent louder than silenceLevel
    let lastFrame = 0;
    let startedAt = 0;
    let lastSample = 0;
    let frame = null;
    let stopTimer = null;

    // ---------- the button and the waveform ----------

    function attach() {
        const found = document.querySelector(BAR_SELECTOR);

        if (!found || (found === host && host.contains(button))) return;

        host = found;
        host.classList.add("hs-voice-host");

        button = document.createElement("button");
        button.type = "button";
        button.className = "hs-voice-button";
        button.innerHTML = MIC_ICON;
        button.addEventListener("click", () => (recording ? stop() : start()));

        wave = document.createElement("div");
        wave.className = "hs-voice-wave";
        wave.setAttribute("aria-hidden", "true");

        bars = Array.from({ length: BAR_COUNT }, () => {
            const bar = document.createElement("span");
            bar.className = "hs-voice-bar";
            wave.appendChild(bar);
            return bar;
        });

        status = document.createElement("span");
        status.className = "hs-voice-status";
        status.textContent = "Transcribing…";
        wave.appendChild(status);

        host.append(button, wave);
        render();
    }

    function render() {
        if (!host) return;

        host.classList.toggle("hs-voice-listening", recording);
        host.classList.toggle("hs-voice-busy", busy);
        button.classList.toggle("hs-voice-active", recording);
        button.disabled = busy;

        const label = recording ? "Stop recording" : "Ask by voice";
        button.setAttribute("aria-label", label);
        button.title = label;
    }

    function drawLevels() {
        bars.forEach((bar, i) => {
            bar.style.height = `${Math.max(DOT, levels[i]) * 100}%`;
        });
    }

    // Redraws of the page can replace the chat bar; put the button back when they do.
    let attachQueued = false;
    new MutationObserver(() => {
        if (attachQueued) return;
        attachQueued = true;
        requestAnimationFrame(() => {
            attachQueued = false;
            attach();
        });
    }).observe(document.body, { childList: true, subtree: true });

    // ---------- recording ----------

    async function start() {
        if (busy) return;

        if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
            report("unsupported");
            return;
        }

        try {
            stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        } catch (error) {
            report(error?.name || "denied");
            return;
        }

        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioContext.createAnalyser();
        analyser.fftSize = 1024;
        audioContext.createMediaStreamSource(stream).connect(analyser);

        const mimeType = MIME_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
        recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        chunks = [];
        recorder.ondataavailable = (event) => event.data.size && chunks.push(event.data);

        levels.fill(0);
        voiced = 0;
        startedAt = lastSample = lastFrame = performance.now();

        recorder.start();
        recording = true;
        render();
        drawLevels();

        document.addEventListener("keydown", onKey, true);
        stopTimer = setTimeout(stop, maxSeconds * 1000);
        frame = requestAnimationFrame(tick);
    }

    function tick(now) {
        if (!recording) return;

        const samples = new Float32Array(analyser.fftSize);
        analyser.getFloatTimeDomainData(samples);

        let sum = 0;
        for (const sample of samples) sum += sample * sample;
        const rms = Math.sqrt(sum / samples.length);

        if (rms >= silenceLevel) voiced += (now - lastFrame) / 1000;
        lastFrame = now;

        if (now - lastSample >= SAMPLE_MS) {
            lastSample = now;
            // Square root so quiet speech still moves the bars visibly.
            levels.push(Math.min(1, Math.sqrt(rms) * 2.2));
            levels.shift();
            drawLevels();
        }

        frame = requestAnimationFrame(tick);
    }

    function onKey(event) {
        if (event.key !== "Enter" || event.isComposing) return;

        // Stop here, and keep Enter from also submitting the empty chat box.
        event.preventDefault();
        event.stopImmediatePropagation();
        stop();
    }

    function release() {
        document.removeEventListener("keydown", onKey, true);
        clearTimeout(stopTimer);
        cancelAnimationFrame(frame);
        stream?.getTracks().forEach((track) => track.stop());
        audioContext?.close();
        stream = audioContext = analyser = null;
    }

    function stop() {
        if (!recording) return;

        recording = false;
        busy = true;
        render();

        const seconds = (performance.now() - startedAt) / 1000;
        recorder.onstop = () => finish(seconds, voiced);
        recorder.stop();
        release();

        // Never leave the button disabled if Python does not answer.
        busyTimer = setTimeout(() => {
            busy = false;
            render();
        }, BUSY_TIMEOUT_MS);
    }

    function finish(seconds, voiced) {
        const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
        const reader = new FileReader();

        reader.onloadend = () => {
            pendingId = `${Date.now()}`;
            send("recording", {
                id: pendingId,
                audio: String(reader.result).split(",")[1] ?? "",
                mime: blob.type,
                seconds,
                voiced,
            });
        };

        reader.readAsDataURL(blob);
    }

    function report(reason) {
        send("unavailable", { id: `${Date.now()}`, reason });
    }

    // ---------- Streamlit ----------

    return {
        update(data, setTriggerValue) {
            send = setTriggerValue;
            maxSeconds = data.max_seconds ?? maxSeconds;
            silenceLevel = data.silence_level ?? silenceLevel;

            // Python has dealt with the recording we sent, so the bar can go back to normal.
            if (busy && pendingId !== null && data.handled === pendingId) {
                busy = false;
                clearTimeout(busyTimer);
            }

            attach();
            render();
        },

        cancel() {
            if (!recording) return;

            recording = false;
            recorder.onstop = null;
            recorder.stop();
            release();
            render();
        },
    };
}
