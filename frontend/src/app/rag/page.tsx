"use client";

import { useState } from "react";

type Citation = { page: number; doc_id: string; chunk_id: string };
type ContextItem = { chunk_id: string; page: number; text: string };

export default function RagTester() {
    // Expose backend to browser via .env.local: NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;

    const [docId, setDocId] = useState<string | null>(null);
    const [question, setQuestion] = useState("");
    const [answer, setAnswer] = useState<string | null>(null);
    const [citations, setCitations] = useState<Citation[]>([]);
    const [contexts, setContexts] = useState<ContextItem[]>([]);
    const [loading, setLoading] = useState(false);
    const [uploading, setUploading] = useState(false);
    const [fileName, setFileName] = useState<string | null>(null);
    const [uploadSuccess, setUploadSuccess] = useState(false);

    if (!backendUrl) {
        return (
            <div className="max-w-xl mx-auto p-6 text-red-600">
                Set <code className="font-mono">NEXT_PUBLIC_BACKEND_URL</code> in <code>.env.local</code>.
            </div>
        );
    }

    // Upload PDF
    async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
        if (!e.target.files?.[0]) return;
        const file = e.target.files[0];
        setFileName(file.name);
        setUploading(true);
        setUploadSuccess(false);
        setDocId(null);
        setAnswer(null);
        setCitations([]);
        setContexts([]);

        const form = new FormData();
        form.append("file", file);

        try {
            const res = await fetch(`${backendUrl}/api/rag/upload`, {
                method: "POST",
                body: form,
            });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            setDocId(data.doc_id);
            setUploadSuccess(true);
        } catch (err: any) {
            alert("Upload failed: " + err.message);
            setFileName(null);
        } finally {
            setUploading(false);
        }
    }

    // Ask a question
    async function handleQuery() {
        if (!docId) {
            alert("Upload a PDF first.");
            return;
        }
        if (!question.trim()) return;

        setLoading(true);
        setAnswer(null);
        setCitations([]);
        setContexts([]);

        try {
            const res = await fetch(`${backendUrl}/api/rag/query`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    doc_id: docId,
                    question,
                    // You can also send overrides like top_k_dense/sparse/final_k/min_dense_sim if needed
                    return_contexts: true,
                }),
            });
            if (!res.ok) throw new Error(await res.text());
            const data = await res.json();
            setAnswer(data.answer);
            setCitations(data.citations || []);
            setContexts(data.contexts || []);
        } catch (err: any) {
            alert("Query failed: " + err.message);
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="max-w-2xl mx-auto p-6 space-y-6 bg-white rounded-lg">
            <div className="flex justify-between items-center gap-2">
                <button
                    onClick={() => {
                        window.location.href = "/"
                    }}
                    className="flex items-center text-gray-600 hover:text-gray-800 transition-colors"
                >
                    <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path>
                    </svg>
                    Back to Home
                </button>
            </div>
            <div className="text-center">
                <div className="text-4xl mb-2">📄</div>
                <h1 className="text-2xl font-bold text-gray-800">RAG Document Assistant</h1>
                <p className="text-gray-600">Upload a PDF and ask questions about its content</p>
            </div>

            {/* Upload Section */}
            <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center transition-colors hover:border-blue-400">
                <input
                    id="file-upload"
                    type="file"
                    accept="application/pdf"
                    onChange={handleUpload}
                    className="hidden"
                />
                <label htmlFor="file-upload" className="cursor-pointer">
                    <div className="flex flex-col items-center justify-center">
                        {uploading ? (
                            <>
                                <div className="w-10 h-10 border-4 border-blue-200 border-t-blue-500 rounded-full animate-spin mb-3"></div>
                                <p className="text-gray-600">Uploading PDF...</p>
                            </>
                        ) : (
                            <>
                                <svg className="w-12 h-12 text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
                                </svg>
                                <p className="text-gray-600">
                                    <span className="text-blue-500 font-medium">Click to upload</span> or drag and drop
                                </p>
                                <p className="text-xs text-gray-500">PDF files only</p>
                            </>
                        )}
                    </div>
                </label>

                {fileName && (
                    <div className={`mt-4 p-3 rounded-md ${uploadSuccess ? "bg-green-50 border border-green-200" : "bg-gray-50 border border-gray-200"}`}>
                        <div className="flex items-center">
                            <svg className={`w-5 h-5 ${uploadSuccess ? "text-green-500" : "text-gray-400"} mr-2`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                            </svg>
                            <span className="text-sm font-medium truncate">{fileName}</span>
                            {uploadSuccess && (
                                <svg className="w-5 h-5 text-green-500 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7"></path>
                                </svg>
                            )}
                        </div>
                        {uploadSuccess && <p className="text-xs text-green-600 mt-1">PDF successfully uploaded and processed</p>}
                    </div>
                )}
            </div>

            {/* Question Input */}
            {docId && (
                <div className="space-y-4">
                    <div className="text-sm text-gray-600">doc_id: <span className="font-mono">{docId}</span></div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Ask a question about the document</label>
                        <div className="flex gap-2">
                            <input
                                type="text"
                                value={question}
                                onChange={(e) => setQuestion(e.target.value)}
                                className="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                                placeholder="Type your question..."
                                onKeyDown={(e) => e.key === "Enter" && handleQuery()}
                            />
                            <button
                                onClick={handleQuery}
                                disabled={loading || !question.trim()}
                                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center min-w-[100px]"
                            >
                                {loading ? (
                                    <>
                                        <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin mr-2"></div>
                                        Searching...
                                    </>
                                ) : (
                                    "Ask"
                                )}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* Answer Section */}
            {answer && (
                <div className="mt-6 border border-gray-200 rounded-lg p-5 bg-gray-50">
                    <h2 className="font-semibold text-lg text-gray-800 mb-3 flex items-center">
                        <svg className="w-5 h-5 text-blue-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"></path>
                        </svg>
                        Answer
                    </h2>
                    <div className="bg-white p-4 rounded-md shadow-sm">
                        <p className="whitespace-pre-line text-gray-700">{answer}</p>
                    </div>

                    {/* Context snippets shown to the LLM */}
                    {!!contexts.length && (
                        <div className="mt-5">
                            <h3 className="font-medium text-gray-700 mb-2">Context used</h3>
                            <ul className="space-y-2">
                                {contexts.map((c, i) => (
                                    <li
                                        key={`${c.chunk_id ?? ""}-${c.page}-${i}`}
                                        className="bg-white p-3 rounded-md border border-gray-200"
                                    >
                                        <div className="text-xs text-gray-500 mb-1">
                                            Page {c.page} • Chunk {c.chunk_id || "(n/a)"}
                                        </div>
                                        <div className="text-sm text-gray-700 whitespace-pre-wrap">{c.text}</div>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    {/* Citations */}
                    {!!citations.length && (
                        <div className="mt-5">
                            <h3 className="font-medium text-gray-700 mb-2 flex items-center">
                                <svg className="w-4 h-4 text-gray-500 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                                </svg>
                                References
                            </h3>
                            <div className="grid gap-2 grid-cols-1 sm:grid-cols-2">
                                {citations.map((c, i) => (
                                    <div key={i} className="bg-white p-3 rounded-md border border-gray-200 text-sm">
                                        <div className="font-medium">Page {c.page}</div>
                                        <div className="text-xs text-gray-500 mt-1">Document: {c.doc_id}</div>
                                        <div className="text-xs text-gray-500">Chunk: {c.chunk_id}</div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Empty State */}
            {!docId && !uploading && (
                <div className="text-center py-8 text-gray-500">
                    <svg className="w-16 h-16 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                    </svg>
                    <p>Upload a PDF document to get started</p>
                </div>
            )}
        </div>
    );
}