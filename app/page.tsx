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

type StructuredDocument = {
  produto: string | null; lote: string | null; data: string | null; nota_fiscal: string | null;
  data_fabricacao: string | null; data_validade: string | null; embalagem: string | null;
  quantidade: string | null; fornecedor: string | null; transportadora: string | null; cliente: string | null;
  tabelas: { secao: string | null; linhas: Array<Record<string, string | null>> }[];
};

type ExtractionResult = ExtractedDocument | StructuredDocument;

const FIELD_LABELS: Record<string, string> = {
  produto: "Produto",
  lote: "Lote",
  data: "Data",
  nota_fiscal: "Nota fiscal",
  data_fabricacao: "Data de fabricação",
  data_validade: "Data de validade",
  embalagem: "Embalagem",
  quantidade: "Quantidade",
  fornecedor: "Fornecedor",
  transportadora: "Transportadora",
  cliente: "Cliente",
};

const COLUMN_LABELS: Record<string, string> = {
  especificacao: "Especificação",
  parametro: "Parâmetro",
  resultado: "Resultado",
  item: "ITEM",
  formula_unid: "FORMULA UNID.",
  metodo_especif: "METODO ESPECIF.",
  analitico: "ANALITICO",
  observacoes: "OBSERVACOES",
};

const CANONICAL_FIVE_COLUMNS = ["item", "formula_unid", "metodo_especif", "analitico", "observacoes"];

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
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [mode, setMode] = useState<"structured" | "text">("structured");
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const structuredResult = result && "tabelas" in result ? result : null;
  const textResult = result && "text" in result ? result : null;
  const isStructured = Boolean(structuredResult);
  const businessEntries = structuredResult
    ? (Object.entries(structuredResult).filter(([key]) => key !== "tabelas") as [string, string | null][])
    : [];

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
    setResult(null);
    const controller = new AbortController();
    abortRef.current = controller;
    const form = new FormData();
    form.append("file", file);
    try {
      const endpoint = mode === "structured" ? "/api/extract/structured" : "/api/extract";
      const response = await fetch(`${API_URL}${endpoint}`, { method: "POST", body: form, signal: controller.signal });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Não foi possível ler este PDF.");
      if (!controller.signal.aborted) setResult(data);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError(reason instanceof Error ? reason.message : "Ocorreu um erro inesperado.");
      }
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
        setIsLoading(false);
      }
    }
  };

  const reset = () => {
    if (isLoading) return;
    setFile(null);
    setResult(null);
    setError("");
    setCopied(false);
    if (inputRef.current) inputRef.current.value = "";
  };

  const copyText = async () => {
    if (!result) return;
    const value = isStructured ? JSON.stringify(result, null, 2) : textResult?.text || "";
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setError("Não foi possível copiar o resultado. Tente selecionar e copiar manualmente.");
    }
  };

  const download = async (format: "txt" | "json" | "pdf") => {
    if (!result) return;
    if (isStructured && format === "json") {
      const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${file?.name.replace(/\.pdf$/i, "") || "resultado"}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      return;
    }
    if (isStructured) return;
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
      anchor.download = `${file?.name.replace(/\.pdf$/i, "") || "resultado"}.${format}`;
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
          <p className="hero-copy">Envie um documento e transforme todas as páginas em texto ou dados estruturados.</p>

          <div className="upload-panel">
            <div className="mode-picker" role="group" aria-label="Modo de extração">
              <button type="button" className={mode === "structured" ? "active" : ""} onClick={() => setMode("structured")} disabled={isLoading} aria-pressed={mode === "structured"}>
                <Braces size={16} /> Laudo estruturado (JSON)
              </button>
              <button type="button" className={mode === "text" ? "active" : ""} onClick={() => setMode("text")} disabled={isLoading} aria-pressed={mode === "text"}>
                <FileText size={16} /> Texto completo
              </button>
            </div>
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
                <button className="remove-file" onClick={() => setFile(null)} disabled={isLoading} aria-label="Remover arquivo"><X size={19} /></button>
                <button className="extract-button" onClick={extract} disabled={isLoading}>
                  {isLoading ? <><LoaderCircle className="spin" size={19} /> Lendo documento...</> : <>{mode === "structured" ? "Extrair laudo estruturado" : "Extrair texto"} <span>→</span></>}
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
              <h1>{isStructured ? "Laudo estruturado" : "Texto extraído"}</h1>
              <p>{file?.name || "Documento enviado"}</p>
            </div>
            <button className="new-file-button" onClick={reset}><RotateCcw size={17} /> Enviar outro PDF</button>
          </div>

          <div className="stats-row">
            <div><span>{isStructured ? "CAMPOS" : "PÁGINAS"}</span><strong>{isStructured ? businessEntries.filter(([, value]) => value !== null).length : textResult?.page_count}</strong></div>
            {isStructured ? <>
              <div><span>TABELAS</span><strong>{structuredResult?.tabelas.length || 0}</strong></div>
              <div><span>LINHAS</span><strong>{structuredResult?.tabelas.reduce((count, table) => count + table.linhas.length, 0) || 0}</strong></div>
              <div className="success-stat"><span><Check size={13} /> CONCLUÍDO</span><strong>OK</strong></div>
            </> : <>
              <div><span>PALAVRAS</span><strong>{textResult?.word_count.toLocaleString("pt-BR")}</strong></div>
              <div><span>CARACTERES</span><strong>{textResult?.character_count.toLocaleString("pt-BR")}</strong></div>
              <div className="success-stat"><span><Check size={13} /> CONCLUÍDO</span><strong>100%</strong></div>
            </>}
          </div>

          {error && <div className="error-message result-error" role="alert">{error}</div>}
          <div className="result-grid">
            <article className="text-card">
              <div className="card-toolbar">
                <div><FileText size={17} /><strong>{isStructured ? "Campos identificados" : "Conteúdo do documento"}</strong></div>
                <button onClick={copyText}>{copied ? <Check size={15} /> : <Copy size={15} />}{copied ? "Copiado" : isStructured ? "Copiar JSON" : "Copiar texto"}</button>
              </div>
              {isStructured ? <div className="structured-content">
                {businessEntries.some(([, value]) => value !== null) ? <dl className="field-list">{businessEntries.map(([key, value]) => <div key={key}><dt>{FIELD_LABELS[key] || key.replace(/_/g, " ")}</dt><dd>{value ?? "—"}</dd></div>)}</dl> : <p className="empty-state">Nenhum campo foi identificado.</p>}
                {structuredResult?.tabelas.map((table, index) => {
                  const discoveredColumns = Array.from(new Set(table.linhas.flatMap((row) => Object.keys(row))));
                  // Canonical five-column tables are positional: API keys are authoritative
                  // even when the source PDF headers are broken or misleading.
                  const columns = CANONICAL_FIVE_COLUMNS.every((column) => discoveredColumns.includes(column)) && discoveredColumns.length === CANONICAL_FIVE_COLUMNS.length
                    ? CANONICAL_FIVE_COLUMNS
                    : discoveredColumns;
                  return <section className="table-section" key={`${table.secao ?? "table"}-${index}`}><h2>{table.secao || `Tabela ${index + 1}`}</h2><div className="table-scroll"><table><thead><tr>{columns.map((column) => <th key={column}>{COLUMN_LABELS[column] || column.replace(/_/g, " ")}</th>)}</tr></thead><tbody>{table.linhas.map((row, rowIndex) => <tr key={rowIndex}>{columns.map((column) => <td key={column}>{row[column] ?? "—"}</td>)}</tr>)}</tbody></table></div></section>;
                })}
                {structuredResult && <details className="raw-json"><summary>Ver JSON bruto</summary><pre>{JSON.stringify(structuredResult, null, 2)}</pre></details>}
              </div> : <textarea value={textResult?.text || ""} readOnly aria-label="Texto extraído do PDF" />}
            </article>

            <aside className="download-card">
              <div className="download-title"><span><Download size={18} /></span><div><strong>Baixar resultado</strong><small>Escolha o formato</small></div></div>
              {!isStructured && <button onClick={() => download("txt")} disabled={!!exporting}>
                <span className="format-icon txt"><FileText size={20} /></span>
                <span><strong>Texto simples</strong><small>.TXT</small></span>
                {exporting === "txt" ? <LoaderCircle className="spin" size={17} /> : <ChevronDown className="download-arrow" size={17} />}
              </button>}
              {!isStructured && <button onClick={() => download("pdf")} disabled={!!exporting}>
                <span className="format-icon pdf"><FileText size={20} /></span>
                <span><strong>Documento PDF</strong><small>.PDF</small></span>
                {exporting === "pdf" ? <LoaderCircle className="spin" size={17} /> : <ChevronDown className="download-arrow" size={17} />}
              </button>}
              <button onClick={() => download("json")} disabled={!!exporting}>
                <span className="format-icon json"><Braces size={20} /></span>
                <span><strong>Dados estruturados</strong><small>.JSON</small></span>
                {exporting === "json" ? <LoaderCircle className="spin" size={17} /> : <ChevronDown className="download-arrow" size={17} />}
              </button>
              <div className="download-note"><FileJson size={15} /> {isStructured ? "JSON pronto para copiar ou baixar." : "Todos os formatos preservam o texto exibido."}</div>
            </aside>
          </div>
        </section>
      )}
    </main>
  );
}
