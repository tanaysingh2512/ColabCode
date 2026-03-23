import type { CollaborationSession, Participant } from "../types";

type PresenceListProps = {
  participants: Participant[];
  session: CollaborationSession | null;
};

export function PresenceList({ participants, session }: PresenceListProps) {
  const sorted = [...participants].sort((left, right) => {
    if (left.sessionId === session?.sessionId) {
      return -1;
    }
    if (right.sessionId === session?.sessionId) {
      return 1;
    }
    return left.displayName.localeCompare(right.displayName);
  });

  return (
    <section className="panel sidebar-panel">
      <div className="panel-heading">
        <h3>Presence</h3>
        <span>{sorted.length} online</span>
      </div>
      <div className="presence-list">
        {sorted.map((participant) => (
          <article className="presence-card" key={participant.sessionId}>
            <span
              className="presence-swatch"
              style={{ backgroundColor: participant.color }}
              aria-hidden="true"
            />
            <div>
              <strong>
                {participant.displayName}
                {participant.sessionId === session?.sessionId ? " (you)" : ""}
              </strong>
              <p>
                {participant.selectionStart === participant.selectionEnd ||
                participant.selectionStart === null ||
                participant.selectionEnd === null
                  ? "Watching"
                  : "Selecting text"}
              </p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
