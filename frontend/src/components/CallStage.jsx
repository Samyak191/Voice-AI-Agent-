import { useEffect, useRef } from "react";

const BAR_WEIGHTS = [0.5, 0.8, 1, 0.8, 0.5];

export default function CallStage({
  connected,
  recording,
  onStart,
  onStop,
  audioPlayer,
  userLevelRef,
  aiTalking,
  interrupted,
}) {
  const userBarsRef = useRef([]);
  const aiBarsRef = useRef([]);
  const lineRef = useRef(null);

  useEffect(() => {
    let frame;

    const tick = () => {
      const userLevel = userLevelRef.current || 0;
      const aiLevel = audioPlayer.getLevel();

      userBarsRef.current.forEach((el, i) => {
        if (!el) return;
        const h = 0.15 + userLevel * BAR_WEIGHTS[i] * 1.8;
        el.style.transform = `scaleY(${Math.min(h, 1.6)})`;
      });

      aiBarsRef.current.forEach((el, i) => {
        if (!el) return;
        const h = 0.15 + aiLevel * BAR_WEIGHTS[i] * 1.8;
        el.style.transform = `scaleY(${Math.min(h, 1.6)})`;
      });

      const active = userLevel > 0.05 || aiLevel > 0.05;
      if (lineRef.current) {
        lineRef.current.style.opacity = active ? "1" : "0.35";
      }

      frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [audioPlayer, userLevelRef]);

  return (
    <div className={`call-stage ${interrupted ? "call-stage--interrupted" : ""}`}>
      <div className="call-status">
        <span
          className={`jack ${connected ? "jack--live" : ""} ${aiTalking ? "jack--speaking" : ""}`}
        />
        <span className="call-status__label">
          {connected
            ? aiTalking
              ? "assistant speaking"
              : recording
              ? "listening"
              : "on the line"
            : "offline"}
        </span>
      </div>

      <div className="call-nodes">
        <div className="node node--user">
          <div className="node__ring">
            <div className="node__bars">
              {[0, 1, 2, 3, 4].map((i) => (
                <span
                  key={i}
                  ref={(el) => (userBarsRef.current[i] = el)}
                  className="bar bar--user"
                />
              ))}
            </div>
          </div>
          <span className="node__label">you</span>
        </div>

        <div ref={lineRef} className="call-line">
          <span className="call-line__pulse" />
        </div>

        <div className="node node--ai">
          <div className="node__ring">
            <div className="node__bars">
              {[0, 1, 2, 3, 4].map((i) => (
                <span
                  key={i}
                  ref={(el) => (aiBarsRef.current[i] = el)}
                  className="bar bar--ai"
                />
              ))}
            </div>
          </div>
          <span className="node__label">assistant</span>
        </div>
      </div>

      <button className="call-button" onClick={recording ? onStop : onStart}>
        {recording ? "end call" : "start call"}
      </button>
    </div>
  );
}