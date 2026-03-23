import { useEffect, useRef, useState } from "react";
import type * as Monaco from "monaco-editor";
import * as Y from "yjs";
import { MonacoBinding } from "y-monaco";

import { buildFileSocketUrl, getFile } from "../lib/api";
import type {
  CollaborationSession,
  ConnectionStatus,
  FileRecord,
  Language,
  Participant,
} from "../types";

const REMOTE_ORIGIN = "remote-sync";

type SnapshotMessage = {
  type: "file.snapshot";
  payload: {
    file: {
      id: string;
      name: string;
      projectId: string;
      projectName: string;
      language: Language;
      shareUrl: string;
    };
    document: string;
    participants: Participant[];
  };
};

type DocumentUpdateMessage = {
  type: "document.update";
  payload: {
    update: string;
    sessionId: string;
    messageId?: string;
  };
};

type AckMessage = {
  type: "document.ack";
  payload: {
    messageId: string;
    processedAt: string;
  };
};

type PresenceMessage =
  | {
      type: "presence.update";
      payload: Participant;
    }
  | {
      type: "presence.leave";
      payload: { sessionId: string };
    };

type LanguageMessage = {
  type: "file.language";
  payload: { language: Language };
};

type ErrorMessage = {
  type: "error";
  payload: { message: string };
};

type ServerMessage =
  | SnapshotMessage
  | DocumentUpdateMessage
  | AckMessage
  | PresenceMessage
  | LanguageMessage
  | ErrorMessage;

function uint8ArrayToBase64(value: Uint8Array): string {
  let binary = "";
  for (let index = 0; index < value.length; index += 1) {
    binary += String.fromCharCode(value[index]);
  }
  return btoa(binary);
}

function base64ToUint8Array(value: string): Uint8Array {
  const binary = atob(value);
  const output = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    output[index] = binary.charCodeAt(index);
  }
  return output;
}

function sanitizeClassName(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, "-");
}

function toFileRecord(payload: SnapshotMessage["payload"]["file"]): FileRecord {
  return {
    id: payload.id,
    projectId: payload.projectId,
    name: payload.name,
    language: payload.language,
    latestStateSize: 0,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    shareUrl: payload.shareUrl,
  };
}

export function useCollaborativeFile(
  fileId: string | undefined,
  authToken: string | null,
  session: CollaborationSession | null,
  onSessionConflict?: () => Promise<void> | void,
) {
  const [file, setFile] = useState<FileRecord | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("connecting");
  const [language, setLanguage] = useState<Language>("python");
  const [error, setError] = useState<string | null>(null);
  const [syncLatencyMs, setSyncLatencyMs] = useState<number | null>(null);

  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof Monaco | null>(null);
  const selectionListenerRef = useRef<Monaco.IDisposable | null>(null);
  const bindingRef = useRef<MonacoBinding | null>(null);
  const yDocRef = useRef<Y.Doc | null>(null);
  const yTextRef = useRef<Y.Text | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const hasConnectedRef = useRef(false);
  const pendingAcksRef = useRef<Map<string, number>>(new Map());
  const participantMapRef = useRef<Map<string, Participant>>(new Map());
  const decorationIdsRef = useRef<string[]>([]);
  const presenceStyleRef = useRef<HTMLStyleElement | null>(null);
  const sessionConflictRef = useRef(onSessionConflict);

  useEffect(() => {
    sessionConflictRef.current = onSessionConflict;
  }, [onSessionConflict]);

  function setParticipantsFromMap(next: Map<string, Participant>) {
    participantMapRef.current = next;
    setParticipants(Array.from(next.values()));
  }

  function ensurePresenceStyleElement() {
    if (!presenceStyleRef.current) {
      const style = document.createElement("style");
      style.setAttribute("data-collabcode-presence", "true");
      document.head.appendChild(style);
      presenceStyleRef.current = style;
    }
  }

  function updatePresenceStyles() {
    ensurePresenceStyleElement();
    const rules = Array.from(participantMapRef.current.values())
      .filter((participant) => participant.sessionId !== session?.sessionId)
      .map((participant) => {
        const suffix = sanitizeClassName(participant.sessionId);
        const safeLabel = participant.displayName.replace(/"/g, '\\"');
        return `
.remote-selection-${suffix} { background: ${participant.color}33; border-bottom: 1px solid ${participant.color}; }
.remote-cursor-${suffix} { border-left: 2px solid ${participant.color}; margin-left: -1px; height: 1.2em; }
.remote-cursor-${suffix}::after { content: "${safeLabel}"; background: ${participant.color}; color: #fff; border-radius: 999px; font-size: 0.72rem; padding: 0.1rem 0.45rem; position: relative; top: -1.7rem; left: 0.1rem; }
`;
      })
      .join("\n");

    if (presenceStyleRef.current) {
      presenceStyleRef.current.textContent = rules;
    }
  }

  function syncRemoteDecorations() {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    const model = editor?.getModel();
    if (!editor || !monaco || !model) {
      return;
    }

    updatePresenceStyles();

    const decorations: Monaco.editor.IModelDeltaDecoration[] = [];
    for (const participant of participantMapRef.current.values()) {
      if (participant.sessionId === session?.sessionId) {
        continue;
      }
      if (participant.selectionStart === null || participant.selectionEnd === null) {
        continue;
      }

      const startOffset = Math.max(0, Math.min(participant.selectionStart, participant.selectionEnd));
      const endOffset = Math.max(0, Math.max(participant.selectionStart, participant.selectionEnd));
      const startPosition = model.getPositionAt(startOffset);
      const endPosition = model.getPositionAt(endOffset);
      const classSuffix = sanitizeClassName(participant.sessionId);

      if (startOffset !== endOffset) {
        decorations.push({
          range: new monaco.Range(
            startPosition.lineNumber,
            startPosition.column,
            endPosition.lineNumber,
            endPosition.column,
          ),
          options: { className: `remote-selection-${classSuffix}` },
        });
      }

      decorations.push({
        range: new monaco.Range(
          endPosition.lineNumber,
          endPosition.column,
          endPosition.lineNumber,
          endPosition.column,
        ),
        options: {
          beforeContentClassName: `remote-cursor-${classSuffix}`,
          stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
        },
      });
    }

    decorationIdsRef.current = editor.deltaDecorations(decorationIdsRef.current, decorations);
  }

  function sendMessage(type: string, payload: Record<string, unknown>) {
    const socket = wsRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return;
    }
    socket.send(JSON.stringify({ type, payload }));
  }

  function sendCurrentPresence() {
    const editor = editorRef.current;
    const model = editor?.getModel();
    const selection = editor?.getSelection();
    if (!model || !selection) {
      sendMessage("presence.update", { selectionStart: null, selectionEnd: null });
      return;
    }

    const selectionStart = model.getOffsetAt(selection.getStartPosition());
    const selectionEnd = model.getOffsetAt(selection.getEndPosition());
    sendMessage("presence.update", { selectionStart, selectionEnd });
  }

  function mountBindingIfReady() {
    const editor = editorRef.current;
    const model = editor?.getModel();
    const yText = yTextRef.current;
    if (!editor || !model || !yText || bindingRef.current) {
      return;
    }

    bindingRef.current = new MonacoBinding(yText, model, new Set([editor]));
    selectionListenerRef.current = editor.onDidChangeCursorSelection(() => {
      window.requestAnimationFrame(sendCurrentPresence);
    });
    syncRemoteDecorations();
  }

  function applyRemoteFile(fileRecord: FileRecord) {
    setFile(fileRecord);
    setLanguage(fileRecord.language);
    const model = editorRef.current?.getModel();
    if (model && monacoRef.current) {
      monacoRef.current.editor.setModelLanguage(model, fileRecord.language);
    }
  }

  useEffect(() => {
    if (!fileId) {
      return;
    }

    let cancelled = false;
    getFile(fileId)
      .then((fileRecord) => {
        if (!cancelled) {
          applyRemoteFile(fileRecord);
        }
      })
      .catch((caughtError: unknown) => {
        if (!cancelled) {
          setError(caughtError instanceof Error ? caughtError.message : "Unable to load file.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [fileId]);

  useEffect(() => {
    if (!fileId || !session || !authToken) {
      return;
    }

    const resolvedFileId = fileId;
    const resolvedSession = session;
    const resolvedAuthToken = authToken;
    let disposed = false;
    ensurePresenceStyleElement();
    setConnectionStatus("connecting");
    reconnectAttemptsRef.current = 0;

    const documentModel = new Y.Doc();
    const yText = documentModel.getText("code");
    yDocRef.current = documentModel;
    yTextRef.current = yText;

    function sendDocumentUpdate(update: Uint8Array) {
      const messageId = crypto.randomUUID();
      pendingAcksRef.current.set(messageId, performance.now());
      sendMessage("document.update", {
        update: uint8ArrayToBase64(update),
        messageId,
      });
    }

    function connectSocket() {
      const socket = new WebSocket(
        buildFileSocketUrl(resolvedFileId, resolvedSession, resolvedAuthToken),
      );
      wsRef.current = socket;

      socket.onopen = () => {
        const wasReconnecting = reconnectAttemptsRef.current > 0;
        setConnectionStatus(wasReconnecting ? "reconnecting" : "connected");
        reconnectAttemptsRef.current = 0;
        setError(null);
      };

      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as ServerMessage;

        if (message.type === "file.snapshot") {
          const snapshot = base64ToUint8Array(message.payload.document);
          Y.applyUpdate(documentModel, snapshot, REMOTE_ORIGIN);
          applyRemoteFile(toFileRecord(message.payload.file));
          setParticipantsFromMap(
            new Map(message.payload.participants.map((participant) => [participant.sessionId, participant])),
          );
          syncRemoteDecorations();

          if (hasConnectedRef.current) {
            sendDocumentUpdate(Y.encodeStateAsUpdate(documentModel));
          }
          hasConnectedRef.current = true;
          sendCurrentPresence();
          return;
        }

        if (message.type === "document.update") {
          Y.applyUpdate(documentModel, base64ToUint8Array(message.payload.update), REMOTE_ORIGIN);
          return;
        }

        if (message.type === "document.ack") {
          const startedAt = pendingAcksRef.current.get(message.payload.messageId);
          if (startedAt !== undefined) {
            setSyncLatencyMs(Math.round(performance.now() - startedAt));
            pendingAcksRef.current.delete(message.payload.messageId);
          }
          return;
        }

        if (message.type === "presence.update") {
          const next = new Map(participantMapRef.current);
          next.set(message.payload.sessionId, message.payload);
          setParticipantsFromMap(next);
          syncRemoteDecorations();
          return;
        }

        if (message.type === "presence.leave") {
          const next = new Map(participantMapRef.current);
          next.delete(message.payload.sessionId);
          setParticipantsFromMap(next);
          syncRemoteDecorations();
          return;
        }

        if (message.type === "file.language") {
          setLanguage(message.payload.language);
          const model = editorRef.current?.getModel();
          if (model && monacoRef.current) {
            monacoRef.current.editor.setModelLanguage(model, message.payload.language);
          }
          return;
        }

        if (message.type === "error") {
          setError(message.payload.message);
        }
      };

      socket.onclose = (event) => {
        if (disposed) {
          return;
        }
        if (event.code === 4001) {
          setError("Session was replaced. Requesting a fresh collaborative session...");
          setConnectionStatus("reconnecting");
          void sessionConflictRef.current?.();
          return;
        }
        setConnectionStatus("disconnected");
        reconnectAttemptsRef.current += 1;
        const waitTime = Math.min(5000, reconnectAttemptsRef.current * 800);
        reconnectTimerRef.current = window.setTimeout(connectSocket, waitTime);
      };

      socket.onerror = () => {
        setError("WebSocket connection failed.");
      };
    }

    const onLocalUpdate = (update: Uint8Array, origin: unknown) => {
      if (origin === REMOTE_ORIGIN) {
        return;
      }
      sendDocumentUpdate(update);
    };

    documentModel.on("update", onLocalUpdate);
    mountBindingIfReady();
    connectSocket();

    return () => {
      disposed = true;
      documentModel.off("update", onLocalUpdate);
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      wsRef.current?.close();
      wsRef.current = null;
      bindingRef.current?.destroy();
      bindingRef.current = null;
      selectionListenerRef.current?.dispose();
      selectionListenerRef.current = null;
      if (editorRef.current) {
        decorationIdsRef.current = editorRef.current.deltaDecorations(decorationIdsRef.current, []);
      }
      yDocRef.current?.destroy();
      yDocRef.current = null;
      yTextRef.current = null;
      pendingAcksRef.current.clear();
      setParticipants([]);
      participantMapRef.current = new Map();
    };
  }, [authToken, fileId, session]);

  function attachEditor(editor: Monaco.editor.IStandaloneCodeEditor, monaco: typeof Monaco) {
    editorRef.current = editor;
    monacoRef.current = monaco;
    mountBindingIfReady();
    syncRemoteDecorations();
  }

  function changeLanguage(nextLanguage: Language) {
    setLanguage(nextLanguage);
    const model = editorRef.current?.getModel();
    if (model && monacoRef.current) {
      monacoRef.current.editor.setModelLanguage(model, nextLanguage);
    }
    sendMessage("file.language", { language: nextLanguage });
  }

  function getCurrentCode() {
    return editorRef.current?.getValue() ?? yTextRef.current?.toString() ?? "";
  }

  return {
    file,
    participants,
    connectionStatus,
    language,
    error,
    syncLatencyMs,
    attachEditor,
    changeLanguage,
    getCurrentCode,
  };
}
