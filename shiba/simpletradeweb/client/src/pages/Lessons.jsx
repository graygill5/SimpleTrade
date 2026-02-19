import React, { useMemo, useState } from "react";
import Card from "../components/Card.jsx";
import { lessons, progressStore } from "../data/lessons.js";

function LessonCard({ l, onComplete }) {
  const completed = progressStore.isCompleted(l.id);
  const [selected, setSelected] = useState(null);
  const [graded, setGraded] = useState(false);
  const [correct, setCorrect] = useState(false);

  function grade() {
    if (selected === null) return;
    const isCorrect = selected === l.quiz.correctIndex;
    setGraded(true);
    setCorrect(isCorrect);
    if (isCorrect && !completed) {
      progressStore.setCompleted(l.id);
      progressStore.addXP(l.rewardXP);
      onComplete?.(l.rewardXP);
    }
  }

  return (
    <Card
      title={l.title}
      right={
        <span className="muted">
          {l.minutes} min • {completed ? "✅ Completed" : "🟡 Not completed"}
        </span>
      }
    >
      <ul style={{marginTop: 8}}>
        {l.content.map((line, i) => (
          <li key={i} style={{marginBottom: 6}}>{line}</li>
        ))}
      </ul>

      <div style={{marginTop: 12, paddingTop: 12, borderTop: "1px solid #23263b"}}>
        <div className="muted" style={{marginBottom: 6}}>Quiz</div>
        <div style={{fontWeight: 600, marginBottom: 6}}>{l.quiz.question}</div>
        <div style={{display: "grid", gap: 8}}>
          {l.quiz.choices.map((c, idx) => (
            <label key={idx} style={{display:"flex", gap:8, alignItems:"center"}}>
              <input
                type="radio"
                name={`q_${l.id}`}
                checked={selected === idx}
                onChange={() => { setSelected(idx); setGraded(false); }}
              />
              <span>{c}</span>
            </label>
          ))}
        </div>
        <div style={{marginTop: 10, display:"flex", gap:8}}>
          <button className="btn" onClick={grade}>Check Answer</button>
          {graded && (
            <span className="muted">
              {correct ? `✅ Correct! +${l.rewardXP} XP` : "❌ Not quite. Try another choice."}
            </span>
          )}
        </div>
        {graded && !correct && (
          <div className="muted" style={{marginTop: 6}}>{l.quiz.explain}</div>
        )}
        {graded && correct && (
          <div className="muted" style={{marginTop: 6}}>{l.quiz.explain}</div>
        )}
      </div>
    </Card>
  );
}

export default function Lessons() {
  const xp = progressStore.getXP();
  const [earned, setEarned] = useState(0);

  const completedCount = useMemo(
    () => lessons.filter(l => progressStore.isCompleted(l.id)).length,
    [earned, xp]
  );

  function onComplete(amount) {
    setEarned(earned + amount);
  }

  return (
    <div>
      <Card
        title="Lessons"
        right={<span className="muted">Total XP: <b>{progressStore.getXP()}</b></span>}
      >
        <div className="row">
          <div>
            <div className="muted">Modules</div>
            <h2 style={{margin:"6px 0"}}>{completedCount} / {lessons.length} completed</h2>
          </div>
          <div>
            <div className="muted">Why this matters</div>
            <p style={{margin:"6px 0"}}>
              Learn trading concepts hands-on: orders, escrow, matching, and risk. Quiz yourself to
              earn XP and unlock ideas to try in the simulator.
            </p>
          </div>
        </div>
      </Card>

      {lessons.map(l => (
        <LessonCard key={l.id} l={l} onComplete={onComplete} />
      ))}
    </div>
  );
}

