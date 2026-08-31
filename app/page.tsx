"use client";

import {
  ArrowLeft,
  Braces,
  Check,
  ChevronDown,
  Copy,
  Download,
  FileJson,
  FileText,
  LoaderCircle,
  RotateCcw,
  UploadCloud,
  X,
} from "lucide-react";
import { DragEvent, useRef, useState } from "react";

type ExtractedDocument = {
  filename: string;
  page_count: number;
  word_count: number;
  character_count: number;
  text: string;
  pages: { page: number; text: string }[];
};

const MAX_FILE_BYTES = 25 * 1024 * 1024;
const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

function humanFileSize(bytes: number) {
  return bytes < 1024 * 1024
    ? `${Math.max(1, Math.round(bytes / 1024))} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function Home() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ExtractedDocument | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);

  const chooseFile = (selected?: File) => {
    if (!selected) return;
    setError("");
    if (selected.type !== "application/pdf" && !selected.name.toLowerCase().endsWith(".pdf")) {
      setError("Escolha um arquivo no formato PDF.");
      return;
    }
    if (selected.size > MAX_FILE_BYTES) {
      setError("O arquivo ultrapassa o limite de 25 MB.");
      return;
    }
    setFile(selected);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    chooseFile(event.dataTransfer.files[0]);
  };

  const extract = async () => {
    if (!file) return;
    setIsLoading(true);
    setError("");
    const form = new FormData();
    form.append("file", file);
    try {
      const response = await fetch(`${API_URL}/api/extract`, { method: "POST", body: form });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Não foi possível ler este PDF.");
      setResult(data);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ocorreu um erro inesperado.");
    } finally {
      setIsLoading(false);
    }
  };

  const reset = () => {
    setFile(null);
    setResult(null);
    setError("");
    if (inputRef.current) inputRef.current.value = "";
  };

  const copyText = async () => {
    if (!result) return;
    await navigator.clipboard.writeText(result.text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  const download = async (format: "txt" | "json" | "pdf") => {
    if (!result) return;
    setExporting(format);
    setError("");
    try {
      const response = await fetch(`${API_URL}/api/export/${format}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(result),
      });
      if (!response.ok) throw new Error("Não foi possível preparar o download.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${result.filename.replace(/\.pdf$/i, "")}.${format}`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Erro ao baixar o arquivo.");
    } finally {
      setExporting(null);
    }
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={reset} aria-label="Voltar ao início">
          <span className="brand-mark"><FileText size={22} strokeWidth={2.4} /></span>
          <span>PDF <span>Extractor</span></span>
        </button>
      </header>

      {!result ? (
        <section className="upload-view">
          <div className="eyebrow"><span /> LEITURA INTELIGENTE DE DOCUMENTOS</div>
          <p className="hero-copy">Envie um documento e transforme todas as páginas em texto.</p>

          <div className="upload-panel">
            {!file ? (
              <div
                className={`dropzone ${isDragging ? "is-dragging" : ""}`}
                onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
                onDragOver={(event) => event.preventDefault()}
                onDragLeave={() => setIsDragging(false)}
                onDrop={onDrop}
                onClick={() => inputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => (event.key === "Enter" || event.key === " ") && inputRef.current?.click()}
              >
                <input ref={inputRef} type="file" accept="application/pdf,.pdf" onChange={(event) => chooseFile(event.target.files?.[0])} hidden />
                <span className="upload-icon"><UploadCloud size={29} /></span>
                <h2>Arraste seu PDF para cá</h2>
                <p>ou <span>selecione um arquivo</span> no seu computador</p>
                <small>PDF · MÁXIMO 25 MB</small>
              </div>
            ) : (
              <div className="selected-file">
                <div className="file-badge"><FileText size={27} /></div>
                <div className="file-info">
                  <strong>{file.name}</strong>
                  <span>{humanFileSize(file.size)} · pronto para leitura</span>
                </div>
                <button className="remove-file" onClick={() => setFile(null)} aria-label="Remover arquivo"><X size={19} /></button>
                <button className="extract-button" onClick={extract} disabled={isLoading}>
                  {isLoading ? <><LoaderCircle className="spin" size={19} /> Lendo documento...</> : <>Extrair texto <span>→</span></>}
                </button>
              </div>
            )}
            {error && <div className="error-message" role="alert">{error}</div>}
          </div>

        </section>
      ) : (
        <section className="result-view">
          <div className="result-heading">
            <div>
              <button className="back-link" onClick={reset}><ArrowLeft size={16} /> Novo documento</button>
              <h1>Texto extraído</h1>
              <p>{result.filename}</p>
            </div>
            <button className="new-file-button" onClick={reset}><RotateCcw size={17} /> Enviar outro PDF</button>
          </div>

          <div className="stats-row">
            <div><span>PÁGINAS</span><strong>{result.page_count}</strong></div>
            <div><span>PALAVRAS</span><strong>{result.word_count.toLocaleString("pt-BR")}</strong></div>
            <div><span>CARACTERES</span><strong>{result.character_count.toLocaleString("pt-BR")}</strong></div>
            <div className="success-stat"><span><Check size={13} /> CONCLUÍDO</span><strong>100%</strong></div>
          </div>

          {error && <div className="error-message result-error" role="alert">{error}</div>}
          <div className="result-grid">
            <article className="text-card">
              <div className="card-toolbar">
                <div><FileText size={17} /><strong>Conteúdo do documento</strong></div>
                <button onClick={copyText}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "Copiado" : "Copiar texto"}</button>
              </div>
              <textarea value={result.text} readOnly aria-label="Texto extraído do PDF" />
            </article>

            <aside className="download-card">
              <div className="download-title"><span><Download size={18} /></span><div><strong>Baixar resultado</strong><small>Escolha o formato</small></div></div>
              <button onClick={() => download("txt")} disabled={!!exporting}>
                <span className="format-icon txt"><FileText size={20} /></span>
                <span><strong>Texto simples</strong><small>.TXT</small></span>
                {exporting === "txt" ? <LoaderCircle className="spin" size={17} /> : <ChevronDown className="download-arrow" size={17} />}
              </button>
              <button onClick={() => download("pdf")} disabled={!!exporting}>
                <span className="format-icon pdf"><FileText size={20} /></span>
                <span><strong>Documento PDF</strong><small>.PDF</small></span>
                {exporting === "pdf" ? <LoaderCircle className="spin" size={17} /> : <ChevronDown className="download-arrow" size={17} />}
              </button>
              <button onClick={() => download("json")} disabled={!!exporting}>
                <span className="format-icon json"><Braces size={20} /></span>
                <span><strong>Dados estruturados</strong><small>.JSON</small></span>
                {exporting === "json" ? <LoaderCircle className="spin" size={17} /> : <ChevronDown className="download-arrow" size={17} />}
              </button>
              <div className="download-note"><FileJson size={15} /> Todos os formatos preservam o texto exibido.</div>
            </aside>
          </div>
        </section>
      )}
    </main>
  );
}
