// src/lib/pdf-config.ts
import { pdfjs } from 'react-pdf';

export function configurePdfJs() {
  pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.js`;
}
