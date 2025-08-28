"use client";

import { useEffect, useRef, useState } from "react";

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL as string;

type Result = {
  qr: boolean;
  brand: "marlboro" | "classic" | "goldflake" | "i don't know";
};

export default function VisionTest() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [res, setRes] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const reset = () => { setRes(null); setErr(null); };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] || null;
    setFile(f);
    reset();
    if (preview) URL.revokeObjectURL(preview);
    setPreview(f ? URL.createObjectURL(f) : null);
  };

  const onAnalyze = async () => {
    if (!file || !backendUrl) return;
    setLoading(true); reset();
    const form = new FormData();
    form.append("image", file);
    try {
      const r = await fetch(`${backendUrl}/api/vision/analyze`, { method: "POST", body: form });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const json = (await r.json()) as Result;
      setRes(json);
    } catch (e: any) {
      setErr(e?.message || "Failed to analyze");
    } finally {
      setLoading(false);
    }
  };

  const onClear = () => {
    setFile(null); reset();
    if (preview) { URL.revokeObjectURL(preview); setPreview(null); }
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Navbar */}
      <div className="w-full bg-white shadow p-4 flex items-center">
        <button onClick={() => (window.location.href = "/")} className="text-blue-600 hover:underline">
          ← Back
        </button>
        <h1 className="ml-4 text-xl font-bold text-gray-800">QR + Brand (LLM)</h1>
      </div>

      <div className="max-w-xl mx-auto mt-8 bg-white rounded-2xl shadow p-6">
        <p className="text-gray-600 mb-4">
          Upload an image. Backend returns <code>{"{ qr: boolean, brand: '...' }"}</code>.
        </p>

        <div
          className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer ${
            preview ? "border-gray-300 bg-gray-50" : "border-blue-300 bg-blue-50 hover:bg-blue-100"
          }`}
          onClick={() => inputRef.current?.click()}
        >
          <input ref={inputRef} type="file" accept="image/*" onChange={onFileChange} className="hidden" />
          {preview ? (
            <div className="relative">
              <img src={preview} alt="preview" className="max-h-64 mx-auto rounded-lg object-contain" />
              {loading && (
                <div className="absolute inset-0 bg-black/40 flex items-center justify-center rounded-lg">
                  <div className="animate-spin h-10 w-10 rounded-full border-b-2 border-white" />
                </div>
              )}
              <p className="text-sm text-gray-600 mt-2">Click to change image</p>
            </div>
          ) : (
            <>
              <div className="mx-auto w-14 h-14 mb-3 text-blue-500">
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <p className="text-gray-700 font-medium">Drag & drop image, or click to browse</p>
              <p className="text-gray-500 text-sm">JPG / PNG / WebP</p>
            </>
          )}
        </div>

        <div className="flex gap-3 mt-5">
          <button
            onClick={onAnalyze}
            disabled={!file || loading}
            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-2 rounded-lg disabled:opacity-50"
          >
            {loading ? "Analyzing…" : "Analyze"}
          </button>
          {file && (
            <button
              onClick={onClear}
              disabled={loading}
              className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
            >
              Clear
            </button>
          )}
        </div>

        {(err || res) && (
          <div className="mt-6 border-t pt-4">
            <h2 className="text-lg font-semibold text-gray-800 mb-2">Result</h2>
            {err ? (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-800">{err}</div>
            ) : res ? (
              <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-1">
                <div><span className="text-gray-700">QR:&nbsp;</span><b>{res.qr ? "present" : "not present"}</b></div>
                <div><span className="text-gray-700">Brand:&nbsp;</span><b>{res.brand}</b></div>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}