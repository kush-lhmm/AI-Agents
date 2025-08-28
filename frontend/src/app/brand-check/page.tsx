"use client";

import { useRef, useState, useEffect } from "react";

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL as string;

type BrandResult = { label: "marlboro" | "classic" | "goldflake" | "i don't know" };
type ApiShape = { result?: string } | BrandResult;

export default function BrandClassifier() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [label, setLabel] = useState<BrandResult["label"] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const reset = () => {
    setLabel(null);
    setError(null);
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0] || null;
    setFile(f);
    reset();
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(f ? URL.createObjectURL(f) : null);
  };

  const parseApi = (data: ApiShape): BrandResult => {
    if ("result" in data && typeof data.result === "string") {
      return JSON.parse(data.result) as BrandResult;
    }
    return data as BrandResult;
  };

  const onScan = async () => {
    if (!file || !backendUrl) return;
    setLoading(true);
    reset();

    const form = new FormData();
    form.append("image", file);

    try {
      const resp = await fetch(`${backendUrl}/api/brand/classify`, {
        method: "POST",
        body: form,
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

      const json: ApiShape = await resp.json();
      const { label } = parseApi(json);
      setLabel(label);
    } catch (e: any) {
      setError(e?.message || "Failed to classify");
    } finally {
      setLoading(false);
    }
  };

  const onClear = () => {
    setFile(null);
    reset();
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 py-8 px-4">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="mb-10 text-center">
          <button
            onClick={() => (window.location.href = "/")}
            className="inline-flex items-center text-blue-600 font-medium hover:text-blue-800 transition-colors mb-4"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Back to Home
          </button>
          <h1 className="text-4xl font-bold text-gray-800 mb-2">Brand Classifier</h1>
          <p className="text-gray-600">Upload an image to classify it into marlboro, classic, goldflake, or i don't know</p>
        </div>

        {/* Main Content Card */}
        <div className="bg-white rounded-2xl shadow-xl p-6 md:p-8">
          {/* Upload Section */}
          <div className="mb-8">
            <div 
              className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all ${
                !previewUrl 
                  ? "border-blue-300 bg-blue-50 hover:bg-blue-100" 
                  : "border-gray-300 bg-gray-50"
              }`}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={onFileChange}
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
                      <div className="absolute inset-0 bg-black bg-opacity-40 flex items-center justify-center rounded-lg">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-white"></div>
                      </div>
                    )}
                  </div>
                  <p className="text-sm text-gray-600 mb-4">Click to change image</p>
                </div>
              ) : (
                <div className="py-8">
                  <div className="mx-auto w-16 h-16 mb-4 text-blue-500">
                    <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                  </div>
                  <p className="text-gray-700 font-medium mb-1">Drag & drop your image here</p>
                  <p className="text-gray-500 text-sm">or click to browse files</p>
                  <p className="text-gray-400 text-xs mt-2">Supports JPG, PNG, GIF</p>
                </div>
              )}
            </div>

            <div className="flex flex-col sm:flex-row gap-3 mt-6">
              <button
                onClick={onScan}
                disabled={!file || loading}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 px-4 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center"
              >
                {loading ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Classifying...
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                    Classify Image
                  </>
                )}
              </button>
              
              {file && (
                <button
                  onClick={onClear}
                  disabled={loading}
                  className="px-4 py-3 border border-gray-300 text-gray-700 font-medium rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          {/* Results Section */}
          {(label || error) && (
            <div className="border-t pt-8">
              <h2 className="text-xl font-semibold text-gray-800 mb-4">Classification Result</h2>
              
              {error ? (
                <div className="bg-red-50 border border-red-200 rounded-xl p-5">
                  <div className="flex items-start">
                    <div className="flex-shrink-0">
                      <svg className="h-6 w-6 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    <div className="ml-3">
                      <h3 className="text-red-800 font-medium">Classification Error</h3>
                      <div className="mt-2 text-red-700 text-sm">
                        <p>{error}</p>
                      </div>
                    </div>
                  </div>
                </div>
              ) : label ? (
                <div className="bg-green-50 border border-green-200 rounded-xl p-5">
                  <div className="flex items-start">
                    <div className="flex-shrink-0">
                      <svg className="h-6 w-6 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                    </div>
                    <div className="ml-3">
                      <h3 className="text-green-800 font-medium">Classification Successful</h3>
                      <div className="mt-3 bg-white rounded-lg p-4">
                        <p className="text-lg font-semibold text-gray-800 capitalize">{label}</p>
                      </div>
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