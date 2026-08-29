import { useRef, useState, useEffect } from "react";
import { useVoiceSocket } from "./hooks/useVoiceSocket";
import { useMicStream } from "./hooks/useMicStream";
import { AudioPlayer } from "./lib/audioPlayer";
import CallStage from "./components/CallStage";
import TranscriptView from "./components/TranscriptView";
import ResponseView from "./components/ResponseView";
import LatencyPanel from "./components/LatencyPanel";

const WS_URL = import.meta.env.VITE_WS_URL;

function App() {
  const audioPlayerRef = useRef(null);
  if (!audioPlayerRef.current) {
    audioPlayerRef.current = new AudioPlayer();
  }

  const { connected, events, sendAudio, sendControl, lastError } =
    useVoiceSocket(WS_URL, audioPlayerRef.current);

  const { recording, start, stop, levelRef } = useMicStream((chunk) => {
    sendAudio(chunk);
  });

  const processedCountRef = useRef(0);
  const [responseText, setResponseText] = useState("");
  const [aiTalking, setAiTalking] = useState(false);
  const [interrupted, setInterrupted] = useState(false);

  useEffect(() => {
    if (events.length <= processedCountRef.current) return;

    const newEvents = events.slice(processedCountRef.current);
    processedCountRef.current = events.length;

    for (const evt of newEvents) {
      if (evt.type === "transcript_final") {
        setResponseText("");
      }

      if (evt.type === "llm_token") {
        setAiTalking(true);
        setResponseText((prev) => prev + evt.text);
      }

      if (evt.type === "latency") {
        setAiTalking(false);
      }

      if (evt.type === "status" && evt.message === "interrupted") {
        audioPlayerRef.current.stopAll();
        setResponseText("");
        setAiTalking(false);
        setInterrupted(true);
        setTimeout(() => setInterrupted(false), 400);
      }
    }
  }, [events]);

  const handleStart = async () => {
    await audioPlayerRef.current.ensureRunning();
    sendControl("start_session");
    await start();
  };

  const handleStop = () => {
    stop();
    sendControl("stop_session");
  };

  const interim = [...events].reverse().find((e) => e.type === "transcript_interim");
  const finals = events.filter((e) => e.type === "transcript_final").map((e) => e.text);
  const latestLatency = [...events].reverse().find((e) => e.type === "latency");

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-header__mark">◉</span>
        <span className="app-header__title">open line</span>
      </header>

      {lastError && <div className="banner banner--error">{lastError}</div>}

      <CallStage
        connected={connected}
        recording={recording}
        onStart={handleStart}
        onStop={handleStop}
        audioPlayer={audioPlayerRef.current}
        userLevelRef={levelRef}
        aiTalking={aiTalking}
        interrupted={interrupted}
      />

      <div className="panels">
        <TranscriptView interim={interim?.text || ""} finals={finals} />
        <ResponseView text={responseText} />
        <LatencyPanel data={latestLatency?.data} />
      </div>
    </div>
  );
}

export default App;