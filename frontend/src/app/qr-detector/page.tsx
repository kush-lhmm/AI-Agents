"use client";

import { useState, useRef, useEffect } from "react";

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL as string;

type QrPayload = { qr: boolean; message: string };
type ApiShape = { result?: string } | QrPayload;

export default function QrScanner() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [verdict, setVerdict] = useState<QrPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // cleanup any created object URLs
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const resetState = () => {
    setVerdict(null);
    setError(null);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0] || null;
    setFile(selected);
    resetState();

    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(selected ? URL.createObjectURL(selected) : null);
  };

  const parseApi = (data: ApiShape): QrPayload => {
    // Backend currently returns: { "result": "{\"qr\": true, \"message\": \"QR code detected\"}" }
    if ("result" in data && typeof data.result === "string") {
      const parsed = JSON.parse(data.result) as QrPayload;
      return parsed;
    }
    // Future-proof: if backend returns the object directly
    return data as QrPayload;
  };

  const handleUpload = async () => {
    if (!file || !backendUrl) return;

    setLoading(true);
    resetState();

    const formData = new FormData();
    formData.append("image", file);

    try {
      const resp = await fetch(`${backendUrl}/api/qr/scan`, {
        method: "POST",
        body: formData,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const data: ApiShape = await resp.json();
      const payload = parseApi(data);
      setVerdict(payload);
    } catch (err: any) {
      setError(err?.message || "Failed to scan QR");
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setFile(null);
    resetState();
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 py-8 px-4">
      <div className="max-w-3xl mx-auto">
        {/* Navbar */}
        <div className="mb-6 flex items-center justify-between">
          <button
            onClick={() => (window.location.href = "/")}
            className="inline-flex items-center text-blue-600 font-medium hover:text-blue-800 transition-colors"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Back
          </button>
          <h1 className="text-2xl md:text-3xl font-bold text-gray-800">QR Code Scanner</h1>
          <div className="w-10" /> {/* spacer */}
        </div>

        <p className="text-gray-600 mb-6 text-center">
          Upload an image to check if it contains a QR code.
        </p>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-xl p-6 md:p-8">
          {/* Uploader */}
          <div
            className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all ${
              !previewUrl ? "border-blue-300 bg-blue-50 hover:bg-blue-100" : "border-gray-300 bg-gray-50"
            }`}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              className="hidden"
            />

            {previewUrl ? (
              <div className="flex flex-col items-center">
                <div className="mb-4 relative">
                  <img
                    src={previewUrl}
                    alt="Preview"
                    className="max-h-64 max-w-full rounded-lg object-contain mx-auto"
                  />
                  {loading && (
                    <div className="absolute inset-0 bg-black/40 flex items-center justify-center rounded-lg">
                      <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white" />
                    </div>
                  )}
                </div>
                <p className="text-sm text-gray-600">Click to choose another image</p>
              </div>
            ) : (
              <div className="py-8">
                <div className="mx-auto w-16 h-16 mb-4 text-blue-500">
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                </div>
                <p className="text-gray-700 font-medium mb-1">Drag & drop your image here</p>
                <p className="text-gray-500 text-sm">or click to browse files</p>
                <p className="text-gray-400 text-xs mt-2">Supports JPG, PNG, WebP</p>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex flex-col sm:flex-row gap-3 mt-6">
            <button
              onClick={handleUpload}
              disabled={!file || loading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-4 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
            >
              {loading ? (
                <>
                  <svg className="animate-spin -ml-1 mr-3 h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0A12 12 0 004 12h0z" />
                  </svg>
                  Scanning…
                </>
              ) : (
                <>
                  <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v1m6 11h2m-6 0v1m-6-1h2M9 5h2m-2 6h2m-2 6h2m4-6h2m-2-6h2m-2 6h2" />
                  </svg>
                  Scan
                </>
              )}
            </button>

            {file && (
              <button
                onClick={handleClear}
                disabled={loading}
                className="px-4 py-3 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
              >
                Clear
              </button>
            )}
          </div>

          {/* Result */}
          {(error || verdict) && (
            <div className="mt-8 border-t pt-6">
              <h2 className="text-lg font-semibold text-gray-800 mb-3">Result</h2>

              {error ? (
                <div className="bg-red-50 border border-red-200 rounded-xl p-5">
                  <div className="flex items-start">
                    <svg className="h-6 w-6 text-red-500 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div className="text-red-800">{error}</div>
                  </div>
                </div>
              ) : verdict ? (
                <div
                  className={`rounded-xl p-5 border ${
                    verdict.qr ? "bg-green-50 border-green-200" : "bg-yellow-50 border-yellow-200"
                  }`}
                >
                  <div className="flex items-start">
                    <svg
                      className={`h-6 w-6 mr-3 ${verdict.qr ? "text-green-600" : "text-yellow-600"}`}
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      {verdict.qr ? (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      ) : (
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2M21 12A9 9 0 113 12a9 9 0 0118 0z" />
                      )}
                    </svg>
                    <div className="text-gray-900 font-medium">
                      {verdict.qr ? "QR code detected" : "No QR code found"}
                      <div className="text-gray-600 text-sm mt-1">{verdict.message}</div>
                    </div>
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}