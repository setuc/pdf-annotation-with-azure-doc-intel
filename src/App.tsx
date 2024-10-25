import React from 'react';
import * as ReactPDF from 'react-pdf';
import { useResizeObserver } from '@wojtekmaj/react-hooks';
import { Upload, FileJson, Download, ZoomIn, ZoomOut, ChevronLeft, ChevronRight, RefreshCw } from 'lucide-react';
import { Loader } from './components/ui/loader';
import { cn } from './lib/utils';
import type { PDFDocumentProxy } from 'pdfjs-dist';

// Import required styles
import 'react-pdf/dist/esm/Page/AnnotationLayer.css';
import 'react-pdf/dist/esm/Page/TextLayer.css';

// Import and configure pdfjs
import { pdfjs } from 'react-pdf';

if (typeof window !== 'undefined' && 'Worker' in window) {
  pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;
}

// Configure PDF options
const options = {
  cMapUrl: `//unpkg.com/pdfjs-dist@${pdfjs.version}/cmaps/`,
  cMapPacked: true,
  standardFontDataUrl: `//unpkg.com/pdfjs-dist@${pdfjs.version}/standard_fonts/`
};

type FileStatus = 'idle' | 'processing' | 'success' | 'error';

interface FileState {
  file: File | null;
  preview: string | null;
  status: FileStatus;
  error?: string;
}

function App() {
  const [pdfState, setPdfState] = React.useState<FileState>({
    file: null,
    preview: null,
    status: 'idle'
  });
  const [jsonState, setJsonState] = React.useState<FileState>({
    file: null,
    preview: null,
    status: 'idle'
  });
  const [processedPdf, setProcessedPdf] = React.useState<string | null>(null);
  const [numPages, setNumPages] = React.useState(1);
  const [currentPage, setCurrentPage] = React.useState(1);
  const [scale, setScale] = React.useState(1.0);
  const [pageSize, setPageSize] = React.useState<PageSize | null>(null);
  const [isProcessing, setIsProcessing] = React.useState(false);
  const [containerRef, setContainerRef] = React.useState<HTMLElement | null>(null);
  const [containerWidth, setContainerWidth] = React.useState<number>();

  const handleZoomIn = React.useCallback(() => {
    setScale(currentScale => Math.min(2.0, currentScale + 0.1));
  }, []);

  const handleZoomOut = React.useCallback(() => {
    setScale(currentScale => Math.max(0.5, currentScale - 0.1));
  }, []);

  const onResize = React.useCallback<ResizeObserverCallback>((entries) => {
    const [entry] = entries;
    if (entry) {
      setContainerWidth(entry.contentRect.width);
    }
  }, []);

  // Calculate page width based on container and scale
  const pageWidth = React.useMemo(() => {
    if (!containerWidth || !pageSize) return undefined;
    return Math.min(containerWidth - 32, pageSize.width * scale); // 32px for padding
  }, [containerWidth, pageSize, scale]);
  
  const onPageLoadSuccess = React.useCallback(({ width, height }: PageSize) => {
    setPageSize({ width, height });
  }, []);

  useResizeObserver(containerRef, {}, onResize);

  const handleFileUpload = React.useCallback(async (event: React.ChangeEvent<HTMLInputElement>, type: 'pdf' | 'json') => {
    const file = event.target.files?.[0];
    if (!file) return;

    const setState = type === 'pdf' ? setPdfState : setJsonState;
    
    setState(prev => ({
      ...prev,
      file,
      preview: type === 'pdf' ? URL.createObjectURL(file) : null,
      status: 'idle',
      error: undefined
    }));
  }, []);

  const handleDownload = React.useCallback(() => {
    if (processedPdf) {
      const link = document.createElement('a');
      link.href = processedPdf;
      link.download = 'processed-document.pdf';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  }, [processedPdf]);

  const processFiles = React.useCallback(async () => {
    if (!pdfState.file || !jsonState.file) return;
  
    try {
      setIsProcessing(true);
      setPdfState(prev => ({ ...prev, status: 'processing' }));
      setJsonState(prev => ({ ...prev, status: 'processing' }));
  
      const pdfBase64 = await readFileAsBase64(pdfState.file);
      const jsonText = await jsonState.file.text();
      const jsonData = JSON.parse(jsonText);
  
      const response = await fetch('/api/parse_form', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          pdf_base64: pdfBase64,
          analyzeResult: jsonData.analyzeResult
        })
      });
  
      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Failed to process files: ${errorText}`);
      }
  
      const data = await response.json();
      setProcessedPdf(`data:application/pdf;base64,${data.processed_pdf}`);
      setPdfState(prev => ({ ...prev, status: 'success' }));
      setJsonState(prev => ({ ...prev, status: 'success' }));
  
    } catch (error) {
      console.error('Processing error:', error);
      const errorMessage = error instanceof Error ? error.message : 'Error processing files';
      setPdfState(prev => ({ ...prev, status: 'error', error: errorMessage }));
      setJsonState(prev => ({ ...prev, status: 'error', error: errorMessage }));
    } finally {
      setIsProcessing(false);
    }
  }, [pdfState.file, jsonState.file]);

  const onDocumentLoadSuccess = React.useCallback((pdf: PDFDocumentProxy): void => {
    setNumPages(pdf.numPages);
    setCurrentPage(1);
  }, []);

  return (
    <main className="fixed inset-0 flex">
      {/* Sidebar */}
      <aside className="w-80 flex-none bg-white border-r border-gray-200 overflow-y-auto">
        <div className="p-6 space-y-6">
          <h1 className="text-2xl font-bold text-gray-900">Document Intelligence Result Processor</h1>
          
          {/* PDF Upload */}
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <Upload className="w-5 h-5" />
              PDF Document
            </h2>
            <label className={cn(
              "flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-lg cursor-pointer",
              "transition-colors duration-200",
              pdfState.status === 'error' ? "border-red-300 bg-red-50" : 
              pdfState.status === 'success' ? "border-green-300 bg-green-50" :
              "border-gray-300 bg-gray-50 hover:bg-gray-100"
            )}>
              <div className="flex flex-col items-center justify-center pt-5 pb-6">
                <Upload className="w-8 h-8 mb-2 text-gray-500" />
                <p className="mb-2 text-sm text-gray-500">
                  <span className="font-semibold">Click to upload</span> or drag and drop
                </p>
                <p className="text-xs text-gray-500">PDF files only</p>
              </div>
              <input
                type="file"
                className="hidden"
                accept="application/pdf"
                onChange={e => handleFileUpload(e, 'pdf')}
              />
            </label>
            {pdfState.file && (
              <p className="text-sm text-gray-600">
                Selected: {pdfState.file.name}
              </p>
            )}
          </div>

          {/* JSON Upload */}
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
              <FileJson className="w-5 h-5" />
              JSON Analysis
            </h2>
            <label className={cn(
              "flex flex-col items-center justify-center w-full h-32 border-2 border-dashed rounded-lg cursor-pointer",
              "transition-colors duration-200",
              jsonState.status === 'error' ? "border-red-300 bg-red-50" : 
              jsonState.status === 'success' ? "border-green-300 bg-green-50" :
              "border-gray-300 bg-gray-50 hover:bg-gray-100"
            )}>
              <div className="flex flex-col items-center justify-center pt-5 pb-6">
                <FileJson className="w-8 h-8 mb-2 text-gray-500" />
                <p className="mb-2 text-sm text-gray-500">
                  <span className="font-semibold">Click to upload</span> or drag and drop
                </p>
                <p className="text-xs text-gray-500">JSON files only</p>
              </div>
              <input
                type="file"
                className="hidden"
                accept="application/json"
                onChange={e => handleFileUpload(e, 'json')}
              />
            </label>
            {jsonState.file && (
              <p className="text-sm text-gray-600">
                Selected: {jsonState.file.name}
              </p>
            )}
          </div>

          {/* Process Button */}
          <button
            onClick={processFiles}
            disabled={isProcessing || !pdfState.file || !jsonState.file}
            className={cn(
              "w-full flex items-center justify-center gap-2 px-6 py-3 rounded-lg font-semibold text-white",
              "transition-colors duration-200",
              isProcessing || !pdfState.file || !jsonState.file
                ? "bg-gray-400 cursor-not-allowed"
                : "bg-blue-600 hover:bg-blue-700"
            )}
          >
            {isProcessing ? (
              <>
                <RefreshCw className="w-5 h-5 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <RefreshCw className="w-5 h-5" />
                Process Files
              </>
            )}
          </button>

          {(pdfState.error || jsonState.error) && (
            <div className="p-4 bg-red-50 rounded-lg text-red-600 text-sm">
              {pdfState.error || jsonState.error}
            </div>
          )}
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 bg-gray-100 flex flex-col overflow-hidden">
        {/* Controls */}
        {(processedPdf || pdfState.preview) && (
          <div className="flex items-center justify-between p-4 bg-white border-b border-gray-200">
            <div className="flex items-center space-x-4">
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage <= 1}
                className="p-2 hover:bg-gray-100 rounded-lg disabled:opacity-50"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <span className="text-gray-700">Page {currentPage} of {numPages}</span>
              <button
                onClick={() => setCurrentPage(p => Math.min(numPages, p + 1))}
                disabled={currentPage >= numPages}
                className="p-2 hover:bg-gray-100 rounded-lg disabled:opacity-50"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
            <div className="flex items-center space-x-4">
              <button
                onClick={handleZoomOut}
                className="p-2 hover:bg-gray-100 rounded-lg"
                disabled={scale <= 0.5}
              >
                <ZoomOut className="w-5 h-5" />
              </button>
              <span className="min-w-[60px] text-center text-gray-700">
                {Math.round(scale * 100)}%
              </span>
              <button
                onClick={handleZoomIn}
                className="p-2 hover:bg-gray-100 rounded-lg"
                disabled={scale >= 2.0}
              >
                <ZoomIn className="w-5 h-5" />
              </button>
              <button
                onClick={handleDownload}
                disabled={!processedPdf}
                className={cn(
                  "flex items-center gap-2 px-4 py-2 rounded-lg",
                  processedPdf 
                    ? "bg-blue-600 hover:bg-blue-700 text-white" 
                    : "bg-gray-300 text-gray-500 cursor-not-allowed"
                )}
              >
                <Download className="w-4 h-4" />
                Download
              </button>
            </div>
          </div>
        )}

        {/* PDF Viewer */}
        <div className="flex-1 overflow-auto p-6">
          <div className="flex justify-center" ref={setContainerRef}>
            {(processedPdf || pdfState.preview) ? (
              <ReactPDF.Document
                file={processedPdf || pdfState.preview}
                onLoadSuccess={onDocumentLoadSuccess}
                loading={
                  <div className="flex items-center justify-center h-full">
                    <Loader size="lg" />
                  </div>
                }
                error={
                  <div className="flex items-center justify-center h-full text-red-500">
                    Error loading PDF
                  </div>
                }
                options={options}
              >
                <ReactPDF.Page
                  pageNumber={currentPage}
                  scale={scale}
                  onLoadSuccess={onPageLoadSuccess}
                  width={pageWidth}
                  loading={<Loader size="lg" />}
                  className="shadow-lg bg-white"
                  renderAnnotationLayer={true}
                  renderTextLayer={true}
                />
              </ReactPDF.Document>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-500">
                <p>Upload a PDF to view it here</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

// Utility function to read file as base64
function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      if (typeof e.target?.result === 'string') {
        const base64 = e.target.result.split(',')[1];
        resolve(base64);
      } else {
        reject(new Error('Failed to read file'));
      }
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default App;