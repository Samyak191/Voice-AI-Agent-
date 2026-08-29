import { useEffect, useRef, useState, useCallback } from "react";

export function useVoiceSocket(url, audioPlayer) {
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState([]);
  const [lastError, setLastError] = useState(null);
  const socketRef = useRef(null);
  const currentGenRef = useRef(0);
  const seqRef = useRef(0);

  useEffect(() => {
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    socketRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setLastError(null);
    };
    ws.onclose = () => {
      setConnected(false);
      setLastError("connection_lost");
    };
    ws.onerror = () => setConnected(false);

    ws.onmessage = (event) => {
      if (typeof event.data === "string") {
        const parsed = JSON.parse(event.data);

        if (parsed.type === "error") {
          setLastError(parsed.code);
        }

        if (parsed.type === "transcript_final") {
          currentGenRef.current += 1;
          seqRef.current = 0;
          audioPlayer.setGeneration(currentGenRef.current);
        }

        setEvents((prev) => [...prev, parsed]);
      } else {
        seqRef.current += 1;
        audioPlayer.push(event.data, seqRef.current, currentGenRef.current);
      }
    };

    return () => {
      ws.close();
    };
  }, [url, audioPlayer]);

  const sendAudio = useCallback((buffer) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(buffer);
    }
  }, []);

  const sendControl = useCallback((type, payload = {}) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type, ...payload }));
    }
  }, []);

  const triggerBargeIn = useCallback(() => {
    audioPlayer.stopAll();
    sendControl("barge_in");
  }, [audioPlayer, sendControl]);

  return { connected, events, sendAudio, sendControl, triggerBargeIn, lastError };
}