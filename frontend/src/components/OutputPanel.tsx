import type { ExecutionResult } from "../types";

type OutputPanelProps = {
  result: ExecutionResult | null;
  isRunning: boolean;
};

export function OutputPanel({ result, isRunning }: OutputPanelProps) {
  return (
    <section className="panel sidebar-panel">
      <div className="panel-heading">
        <h3>Output</h3>
        <span>{isRunning ? "Running..." : result ? `${result.durationMs} ms` : "Idle"}</span>
      </div>
      <div className="output-block">
        {!result && !isRunning ? (
          <p className="muted">Run the current buffer to see stdout, stderr, and exit status.</p>
        ) : null}
        {result ? (
          <>
            <p>
              Exit code: <strong>{result.exitCode}</strong>
              {result.timedOut ? " (timed out)" : ""}
            </p>
            <pre>{result.stdout || "(no stdout)"}</pre>
            {result.stderr ? <pre className="error-output">{result.stderr}</pre> : null}
          </>
        ) : null}
      </div>
    </section>
  );
}
