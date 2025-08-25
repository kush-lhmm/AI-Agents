"use client";

import React, { useMemo, useRef, useState } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";

type BBox = { x0: number; y0: number; x1: number; y1: number };

type Hair = {
  style: string;
  length: string;
  color: string;
};

type Eyes = {
  color: string;
  eyewear: string;
};

type FacialHair = {
  presence: string;
};

type Expression = {
  mood: string;
  mouth_open: boolean;
  smiling: boolean;
};

type Pose = {
  view: string;
  head_tilt: string;
};

type FaceAttributes = {
  bbox: BBox;
  occluded: boolean;
  age_bracket: string;
  hair: Hair;
  eyes: Eyes;
  facial_hair: FacialHair;
  headwear: string;
  expression: Expression;
  pose: Pose;
  accessories: string[];
};

type PeopleSummary = {
  has_person: boolean;
  num_faces: number;
  faces: FaceAttributes[];
};

type Environment = {
  setting: string;
  dominant_colors: string[]; // color names
};

type Safety = {
  nsfw: boolean;
  minors_possible: boolean;
  sensitive_context: boolean;
};

type PersonImageAnalysis = {
  caption: string;
  people: PeopleSummary;
  environment: Environment;
  ocr_text: string;
  suggested_actions: string[];
  safety: Safety;
};

const ALLOWED_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_BYTES = 5 * 1024 * 1024; // 5MB UI cap (backend allows ~6MB)

export default function ImageAnalyzer() {
  const [selectedPreview, setSelectedPreview] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [goal, setGoal] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<PersonImageAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);

  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;

  // For bbox overlay sizing
  const imgWrapRef = useRef<HTMLDivElement | null>(null);

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    setAnalysis(null);
    const file = e.target.files?.[0] || null;
    if (!file) {
      setSelectedFile(null);
      setSelectedPreview(null);
      return;
    }
    if (!ALLOWED_TYPES.includes(file.type)) {
      setError("Unsupported file type. Use PNG, JPG, or WEBP.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("File too large. Max 5MB.");
      return;
    }
    setSelectedFile(file);
    const reader = new FileReader();
    reader.onload = () => setSelectedPreview(reader.result as string);
    reader.readAsDataURL(file);
  };

  const handleAnalyze = async () => {
    setError(null);
    setAnalysis(null);

    if (!backendUrl) {
      setError("NEXT_PUBLIC_BACKEND_URL is not set.");
      return;
    }
    if (!selectedFile) {
      setError("Please select an image first.");
      return;
    }

    const form = new FormData();
    form.append("image", selectedFile);
    if (goal.trim()) form.append("goal", goal.trim());

    try {
      setIsAnalyzing(true);
      const res = await fetch(
        `${backendUrl.replace(/\/+$/, "")}/api/image/analyze`,
        { method: "POST", body: form }
      );

      if (!res.ok) {
        const text = await res.text();
        if (res.status === 400) throw new Error(text || "Bad request (check file type/size).");
        if (res.status === 413) throw new Error("File too large (server limit).");
        throw new Error(text || `Request failed (${res.status}).`);
      }

      const data = (await res.json()) as PersonImageAnalysis;
      if (!data || typeof data !== "object" || !("caption" in data) || !("people" in data)) {
        throw new Error("Unexpected response format.");
      }
      setAnalysis(data);
    } catch (e: any) {
      setError(e?.message || "Analysis failed.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const clearImage = () => {
    setSelectedFile(null);
    setSelectedPreview(null);
    setAnalysis(null);
    setError(null);
  };

  const faces = analysis?.people?.faces || [];

  // Convert normalized bbox -> percentage styles
  const bboxToStyle = (bbox: BBox) => {
    const left = Math.max(0, Math.min(100, bbox.x0 * 100));
    const top = Math.max(0, Math.min(100, bbox.y0 * 100));
    const width = Math.max(0, Math.min(100, (bbox.x1 - bbox.x0) * 100));
    const height = Math.max(0, Math.min(100, (bbox.y1 - bbox.y0) * 100));
    return { left: `${left}%`, top: `${top}%`, width: `${width}%`, height: `${height}%` };
    // Note: container must be position: relative and track the image dimensions.
  };

  const envColors = useMemo(
    () => analysis?.environment?.dominant_colors ?? [],
    [analysis]
  );

  return (
    <div className="min-h-screen bg-gray-50">
      <motion.header
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="sticky top-0 z-10 bg-white/80 backdrop-blur border-b border-gray-300"
      >
        <div className="max-w-3xl mx-auto px-4 py-5 flex justify-between items-center">
          <Link
            href="/"
            className="flex items-center text-gray-600 hover:text-gray-900 transition-colors group"
          >
            <motion.div whileHover={{ x: -3 }} className="flex items-center">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-4 w-4 mr-1 group-hover:text-blue-500 transition-colors"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="ml-1 group-hover:text-blue-500 transition-colors">Back</span>
            </motion.div>
          </Link>
          <motion.h1
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
            className="text-2xl font-semibold text-gray-800 flex items-center"
          >
            <span>🖼️</span>
            <span className="ml-2">Image Analyzer</span>
          </motion.h1>
          <div className="w-14" />
        </div>
      </motion.header>

      <main className="max-w-3xl mx-auto px-4 py-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="bg-white p-6 rounded-xl border border-gray-300 shadow-md mb-8"
        >
          <h2 className="text-xl font-semibold mb-4 text-gray-800">Upload an Image</h2>

          <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center">
            {selectedPreview ? (
              <motion.div
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                className="mb-4"
              >
                {/* Image container for bbox overlays */}
                <div ref={imgWrapRef} className="relative inline-block">
                  <motion.img
                    src={selectedPreview}
                    alt="Preview"
                    className="max-h-96 mx-auto rounded-md"
                    whileHover={{ scale: 1.01 }}
                  />
                  {/* BBoxes */}
                  {analysis?.people?.faces?.length
                    ? analysis.people.faces.map((f, idx) => (
                        <div
                          key={`bbox-${idx}`}
                          className="absolute border-2 border-blue-500/80 rounded-md pointer-events-none"
                          style={bboxToStyle(f.bbox)}
                          title={`Face ${idx + 1}`}
                        />
                      ))
                    : null}
                </div>

                <motion.button
                  onClick={clearImage}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className="ml-4 text-sm bg-red-100 border py-2 px-5 rounded-xl text-red-500 hover:text-red-600 hover:cursor-pointer"
                >
                  Remove Image
                </motion.button>
              </motion.div>
            ) : (
              <motion.label className="cursor-pointer" whileHover={{ scale: 1.01 }}>
                <div className="flex flex-col items-center justify-center">
                  <motion.div animate={{ y: [0, -5, 0] }} transition={{ repeat: Infinity, duration: 3 }}>
                    <svg className="w-12 h-12 text-gray-400 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                      />
                    </svg>
                  </motion.div>
                  <p className="mb-2 text-sm text-gray-600">Click to upload or drag and drop</p>
                  <p className="text-xs text-gray-800">PNG, JPG, WEBP (MAX. 5MB)</p>
                </div>
                <input
                  type="file"
                  className="hidden"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={handleImageUpload}
                />
              </motion.label>
            )}
          </div>

          <motion.button
            onClick={handleAnalyze}
            disabled={!selectedFile || isAnalyzing}
            whileHover={!selectedFile || isAnalyzing ? {} : { scale: 1.02 }}
            whileTap={!selectedFile || isAnalyzing ? {} : { scale: 0.98 }}
            className={`mt-4 w-full py-3 px-4 rounded-lg font-medium text-white ${
              selectedFile ? "bg-indigo-500 hover:bg-indigo-600" : "bg-gray-300 cursor-not-allowed"
            } transition-colors`}
          >
            {isAnalyzing ? (
              <span className="flex items-center justify-center gap-2">
                <motion.span animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: "linear" }} className="inline-block">
                  🔄
                </motion.span>
                Analyzing...
              </span>
            ) : (
              "Analyze Image"
            )}
          </motion.button>

          <AnimatePresence>
            {error && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-4 text-sm text-red-700 bg-red-50 border border-red-200 p-3 rounded-lg overflow-hidden"
              >
                {error}
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>

        <AnimatePresence>
          {analysis && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="bg-white p-6 rounded-xl shadow-sm border border-gray-300 space-y-6"
            >
              <h2 className="text-xl font-semibold text-gray-900">Image Analysis</h2>

              {/* Caption + Environment */}
              <div className="grid md:grid-cols-2 gap-5">
                <section>
                  <h3 className="text-xs font-bold text-gray-800 uppercase tracking-wider">Caption</h3>
                  <p className="text-gray-700 mt-1">{analysis.caption}</p>
                </section>

                <section>
                  <h3 className="text-xs font-bold text-gray-800 uppercase tracking-wider">Environment</h3>
                  <p className="text-gray-700 mt-1">
                    Setting: <span className="font-medium">{analysis.environment?.setting || "unclear"}</span>
                  </p>
                  <div className="flex items-center gap-1 h-8 mt-2">
                    {envColors.length ? (
                      envColors.map((c, i) => (
                        <div
                          key={`${c}-${i}`}
                          className="h-full flex-1 rounded-sm border border-gray-300"
                          style={{ backgroundColor: c }}
                          title={c}
                        />
                      ))
                    ) : (
                      <span className="text-gray-500 text-sm">No colors extracted</span>
                    )}
                  </div>
                </section>

                {/* OCR */}
                <section className="md:col-span-2">
                  <h3 className="text-xs font-bold text-gray-800 uppercase tracking-wider">Text (OCR)</h3>
                  <div className="p-2 bg-gray-50 rounded-lg border border-gray-300 mt-1">
                    <p className="text-gray-700 whitespace-pre-wrap">
                      {analysis.ocr_text?.trim() || <span className="text-gray-500">No text found</span>}
                    </p>
                  </div>
                </section>

                {/* People summary */}
                <section className="md:col-span-2">
                  <h3 className="text-xs font-bold text-gray-800 uppercase tracking-wider">People</h3>
                  <p className="text-gray-700 mt-1">
                    Present:{" "}
                    <span className={`font-medium ${analysis.people?.has_person ? "text-blue-700" : "text-gray-600"}`}>
                      {analysis.people?.has_person ? "Yes" : "No"}
                    </span>{" "}
                    {analysis.people?.has_person ? `• Faces: ${analysis.people?.num_faces ?? 0}` : null}
                  </p>
                </section>

                {/* Faces grid */}
                {faces.length > 0 && (
                  <section className="md:col-span-2">
                    <div className="grid md:grid-cols-2 gap-4">
                      {faces.map((f, i) => (
                        <div key={`face-${i}`} className="border border-gray-300 rounded-lg p-3">
                          <div className="flex items-center justify-between">
                            <h4 className="text-sm font-semibold text-gray-900">Face #{i + 1}</h4>
                            <span className="text-xs text-gray-500">
                              BBox: [{f.bbox.x0.toFixed(2)}, {f.bbox.y0.toFixed(2)} → {f.bbox.x1.toFixed(2)}, {f.bbox.y1.toFixed(2)}]
                            </span>
                          </div>
                          <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
                            <div>
                              <div className="text-gray-500">Age</div>
                              <div className="font-medium">{f.age_bracket}</div>
                            </div>
                            <div>
                              <div className="text-gray-500">Occluded</div>
                              <div className="font-medium">{f.occluded ? "Yes" : "No"}</div>
                            </div>
                            <div>
                              <div className="text-gray-500">Hair</div>
                              <div className="font-medium">
                                {f.hair.style}, {f.hair.length}, {f.hair.color}
                              </div>
                            </div>
                            <div>
                              <div className="text-gray-500">Eyes</div>
                              <div className="font-medium">
                                {f.eyes.color} {f.eyes.eyewear !== "none" ? `• ${f.eyes.eyewear}` : ""}
                              </div>
                            </div>
                            <div>
                              <div className="text-gray-500">Facial Hair</div>
                              <div className="font-medium">{f.facial_hair.presence}</div>
                            </div>
                            <div>
                              <div className="text-gray-500">Headwear</div>
                              <div className="font-medium">{f.headwear}</div>
                            </div>
                            <div>
                              <div className="text-gray-500">Expression</div>
                              <div className="font-medium">
                                {f.expression.mood}
                                {f.expression.smiling ? " • smiling" : ""}
                                {f.expression.mouth_open ? " • mouth open" : ""}
                              </div>
                            </div>
                            <div>
                              <div className="text-gray-500">Pose</div>
                              <div className="font-medium">
                                {f.pose.view} • {f.pose.head_tilt}
                              </div>
                            </div>
                            <div className="col-span-2">
                              <div className="text-gray-500">Accessories</div>
                              <div className="font-medium">
                                {f.accessories?.length ? f.accessories.join(", ") : "None"}
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                )}

                {/* Safety */}
                <section className="md:col-span-2">
                  <h3 className="text-xs font-bold text-gray-800 uppercase tracking-wider">Content Safety</h3>
                  <div className="grid grid-cols-3 gap-3 mt-2">
                    <div className={`p-2.5 rounded-lg border ${analysis.safety?.nsfw ? "bg-red-50 border-red-200" : "bg-green-50 border-green-200"}`}>
                      <div className="flex items-center gap-2">
                        <div className={`w-3 h-3 rounded-full ${analysis.safety?.nsfw ? "bg-red-500" : "bg-green-500"}`} />
                        <span className="text-sm font-medium text-gray-800">NSFW</span>
                      </div>
                      <p className="mt-1 text-xs text-gray-500 pl-5">
                        {analysis.safety?.nsfw ? "Detected" : "Not detected"}
                      </p>
                    </div>

                    <div className={`p-2.5 rounded-lg border ${analysis.safety?.minors_possible ? "bg-yellow-50 border-yellow-200" : "bg-gray-50 border-gray-200"}`}>
                      <div className="flex items-center gap-2">
                        <div className={`w-3 h-3 rounded-full ${analysis.safety?.minors_possible ? "bg-yellow-500" : "bg-gray-400"}`} />
                        <span className="text-sm font-medium text-gray-800">Minors Possible</span>
                      </div>
                      <p className="mt-1 text-xs text-gray-500 pl-5">
                        {analysis.safety?.minors_possible ? "Maybe" : "Unlikely"}
                      </p>
                    </div>

                    <div className={`p-2.5 rounded-lg border ${analysis.safety?.sensitive_context ? "bg-orange-50 border-orange-200" : "bg-gray-50 border-gray-200"}`}>
                      <div className="flex items-center gap-2">
                        <div className={`w-3 h-3 rounded-full ${analysis.safety?.sensitive_context ? "bg-orange-500" : "bg-gray-400"}`} />
                        <span className="text-sm font-medium text-gray-800">Sensitive Context</span>
                      </div>
                      <p className="mt-1 text-xs text-gray-500 pl-5">
                        {analysis.safety?.sensitive_context ? "Detected" : "Not detected"}
                      </p>
                    </div>
                  </div>
                </section>
              </div>

              {/* Suggested Actions */}
              <section>
                <h3 className="text-xs font-bold text-gray-800 uppercase tracking-wider">Suggested Actions</h3>
                <div className="flex flex-wrap gap-2 mt-2">
                  {analysis.suggested_actions?.length ? (
                    analysis.suggested_actions.map((s, i) => (
                      <motion.span
                        key={`${s}-${i}`}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.05 * i }}
                        whileHover={{ scale: 1.05 }}
                        className="px-3 py-1.5 bg-gray-50 rounded-lg text-sm text-gray-700 border border-gray-300"
                      >
                        {s}
                      </motion.span>
                    ))
                  ) : (
                    <span className="text-gray-400 text-sm">No suggestions</span>
                  )}
                </div>
              </section>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
