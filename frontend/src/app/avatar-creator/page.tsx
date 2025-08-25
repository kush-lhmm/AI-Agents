"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FiImage, FiArrowRight, FiDownload, FiExternalLink } from "react-icons/fi";

interface AvatarResponse {
  url: string;
  format: string;
  aspect_ratio: string;
}

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1
    }
  }
};

const itemVariants = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0 }
};

export default function AvatarCreator() {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [fileObj, setFileObj] = useState<File | null>(null);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const backend = process.env.NEXT_PUBLIC_BACKEND_URL;

  const ALLOWED_TYPES = new Set([
    "image/png",
    "image/jpeg",
    "image/webp",
  ]);

  const triggerFileInput = () => fileInputRef.current?.click();

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!ALLOWED_TYPES.has(file.type)) {
      setError("Only PNG, JPG, WEBP, or HEIC are allowed.");
      setFileObj(null);
      setPreviewUrl(null);
      return;
    }

    if (file.size > 8 * 1024 * 1024) {
      setError("Image must be under 8MB.");
      setFileObj(null);
      setPreviewUrl(null);
      return;
    }

    setError(null);
    setFileObj(file);
    setResultUrl(null);

    const url = URL.createObjectURL(file);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(url);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!backend) {
      setError("NEXT_PUBLIC_BACKEND_URL is not set.");
      return;
    }
    if (!fileObj || !instruction.trim()) {
      setError("Please provide both an image and instructions.");
      return;
    }

    setIsLoading(true);
    setError(null);
    setResultUrl(null);

    try {
      const fd = new FormData();
      fd.append("prompt", instruction.trim());
      fd.append("image", fileObj);

      const res = await fetch(`${backend}/api/avatar`, {
        method: "POST",
        body: fd,
      });

      if (!res.ok) {
        const txt = await res.text();
        throw new Error(txt || `HTTP ${res.status}`);
      }

      const data = await res.json() as AvatarResponse;
      if (!data?.url) throw new Error("Invalid response from server.");

      await new Promise(resolve => setTimeout(resolve, 500));
      setResultUrl(data.url);
    } catch (err: any) {
      console.error(err);
      setError(err?.message || "Failed to transform image.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownload = () => {
    if (!resultUrl) return;
    const a = document.createElement("a");
    a.href = resultUrl;
    a.download = "avatar.png";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  return (
    <motion.main
      initial="hidden"
      animate="show"
      variants={containerVariants}
      className="min-h-screen bg-gradient-to-br from-gray-100 to-gray-200 py-10 px-4"
    >
      <div className="mx-auto w-full max-w-3xl">
        <motion.header
          variants={itemVariants}
          className="text-center mb-8"
        >
          <motion.h1
            initial={{ scale: 0.9 }}
            animate={{ scale: 1 }}
            transition={{ type: "spring", stiffness: 200 }}
            className="text-3xl font-bold text-gray-900 mb-2"
          >
            🎨 Avatar Creator
          </motion.h1>
          <motion.p
            whileHover={{ scale: 1.02 }}
            className="text-gray-600 text-lg"
          >
            Snap. Describe. Transform! Your avatar awaits 🚀
          </motion.p>
        </motion.header>

        <motion.div
          variants={itemVariants}
          className="bg-white rounded-xl shadow-lg overflow-hidden"
        >
          <form onSubmit={handleSubmit} className="p-6 sm:p-8 space-y-6">

            <motion.div variants={itemVariants}>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Upload Your Photo
              </label>
              <motion.div
                onClick={triggerFileInput}
                className="mt-1 flex justify-center px-6 pt-5 pb-6 border-2 border-dashed border-gray-300 rounded-lg cursor-pointer hover:border-blue-500 transition-colors"
                whileHover={{ scale: 1.01 }}
                whileTap={{ scale: 0.98 }}
              >
                <div className="text-center">
                  {previewUrl ? (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="relative mx-auto overflow-hidden"
                    >
                      <img
                        src={previewUrl}
                        alt="Preview"
                        className="object-cover w-40 h-auto rounded-lg"
                      />
                    </motion.div>
                  ) : (
                    <motion.div
                      initial={{ opacity: 0.5 }}
                      animate={{ opacity: 1 }}
                      className="space-y-2"
                    >
                      <FiImage className="mx-auto h-12 w-12 text-gray-400" />
                      <p className="mt-2 text-sm text-gray-600">
                        <span className="font-medium text-blue-600">Click to upload</span> or drag & drop
                      </p>
                      <p className="text-xs text-gray-500">PNG, JPG, WEBP (Max 8MB)</p>
                    </motion.div>
                  )}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/heic,image/heif"
                    onChange={handleImageUpload}
                    className="sr-only"
                  />
                </div>
              </motion.div>
            </motion.div>

            {/* Instruction Section */}
            <motion.div variants={itemVariants}>
              <label htmlFor="instruction" className="block text-sm font-medium text-gray-700 mb-2">
                Transformation Instructions
              </label>
              <motion.textarea
                id="instruction"
                rows={3}
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                placeholder="Example: 'Turn me into a cyberpunk character' or 'Make me look like a watercolor painting'"
                className="block w-full rounded-lg border border-gray-300 p-3 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                whileFocus={{ scale: 1.005, boxShadow: "0 0 0 2px rgba(59, 130, 246, 0.5)" }}
              />
            </motion.div>

            {/* Error Message */}
            <AnimatePresence>
              {error && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="rounded-lg bg-red-50 p-4 overflow-hidden"
                >
                  <p className="text-sm text-red-800">{error}</p>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Submit Button */}
            <motion.div variants={itemVariants}>
              <motion.button
                type="submit"
                disabled={isLoading || !fileObj || !instruction.trim()}
                className={`w-full py-3 rounded-lg text-sm font-medium text-white shadow-lg flex items-center justify-center gap-2 ${isLoading || !fileObj || !instruction.trim()
                  ? "bg-blue-300 cursor-not-allowed"
                  : "bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700"
                  }`}
                whileHover={(!isLoading && fileObj && instruction.trim()) ? { scale: 1.02 } : {}}
                whileTap={(!isLoading && fileObj && instruction.trim()) ? { scale: 0.98 } : {}}
              >
                {isLoading ? (
                  <>
                    <motion.span
                      animate={{ rotate: 360 }}
                      transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
                      className="h-4 w-4 border-2 border-white border-t-transparent rounded-full"
                    />
                    Creating Magic...
                  </>
                ) : (
                  <>
                    Create My Avatar <FiArrowRight />
                  </>
                )}
              </motion.button>
            </motion.div>
          </form>
        </motion.div>

        {/* Results Section */}
        <AnimatePresence>
          {resultUrl && (
            <motion.section
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 20 }}
              transition={{ type: "spring", stiffness: 300 }}
              className="mt-8 bg-white rounded-xl shadow-lg overflow-hidden p-6 sm:p-8"
            >
              <h2 className="text-lg font-semibold text-gray-900 mb-4">✨ Your Transformed Avatar</h2>

              <div className="flex flex-col sm:flex-row items-center justify-center gap-8 mb-6">
                {previewUrl && (
                  <motion.div
                    className="text-center"
                    whileHover={{ scale: 1.03 }}
                  >
                    <p className="text-sm text-gray-500 mb-2">Original</p>
                    <div className="relative h-40 w-40 rounded-full overflow-hidden border-2 border-gray-200 shadow-md">
                      <img src={previewUrl} alt="Original" className="object-cover" />
                    </div>
                  </motion.div>
                )}

                <motion.div
                  className="text-center"
                  initial={{ scale: 0.9 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: 0.2 }}
                >
                  <p className="text-sm text-gray-500 mb-2">Transformed</p>
                  <div className="relative h-40 w-40 rounded-full overflow-hidden border-2 border-blue-200 shadow-lg">
                    <img src={resultUrl} alt="Avatar" className="object-cover" />
                  </div>
                </motion.div>
              </div>

              <div className="flex flex-col sm:flex-row justify-center gap-3">
                <motion.a
                  href={resultUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center justify-center px-4 py-2 rounded-lg text-sm font-medium text-white bg-gray-700 hover:bg-gray-800 gap-2"
                  whileHover={{ y: -2 }}
                  whileTap={{ scale: 0.98 }}
                >
                  Open in new tab <FiExternalLink />
                </motion.a>

                <motion.button
                  onClick={handleDownload}
                  className="inline-flex items-center justify-center px-4 py-2 rounded-lg text-sm font-medium text-white bg-gradient-to-r from-green-600 to-teal-600 hover:from-green-700 hover:to-teal-700 gap-2"
                  whileHover={{ y: -2 }}
                  whileTap={{ scale: 0.98 }}
                >
                  Download Avatar <FiDownload />
                </motion.button>
              </div>
            </motion.section>
          )}
        </AnimatePresence>
      </div>
    </motion.main>
  );
}