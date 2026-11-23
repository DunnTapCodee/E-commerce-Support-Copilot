import { apiClient } from './api-client';

/**
 * Utility to parse plain text content from various file formats.
 * For binary/OpenXML documents (.docx, .pdf), calls backend parser for 100% clean text extraction.
 * For text files (.txt, .md, .json, .csv), decodes directly in browser.
 */

export async function extractTextFromFile(file: File): Promise<string> {
  const extension = file.name.split('.').pop()?.toLowerCase() || '';

  // 1. Word .docx, .doc or binary files: Call backend parser endpoint with ZIP/XML support
  if (['docx', 'doc', 'pdf'].includes(extension) || file.type.includes('word') || file.type.includes('pdf')) {
    try {
      const parsed = await apiClient.parseDocumentFile(file);
      if (parsed && parsed.text && parsed.text.trim()) {
        return parsed.text.trim();
      }
    } catch (err) {
      console.warn(`Backend parse failed for ${file.name}, trying local extraction:`, err);
    }
  }

  // 2. Standard text files (.txt, .md, .csv, .log, .xml, .html)
  if (['txt', 'md', 'csv', 'log', 'xml', 'html', 'rtf'].includes(extension) || file.type.startsWith('text/')) {
    return await file.text();
  }

  // 3. JSON files (.json)
  if (extension === 'json' || file.type === 'application/json') {
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        return parsed
          .map((item, idx) => {
            if (typeof item === 'string') return item;
            if (item && typeof item === 'object') {
              return item.content || item.raw_text || item.title || JSON.stringify(item, null, 2);
            }
            return `Chính sách ${idx + 1}: ${String(item)}`;
          })
          .join('\n\n---\n\n');
      }
      if (parsed && typeof parsed === 'object') {
        if (parsed.policies && Array.isArray(parsed.policies)) {
          return parsed.policies
            .map((p: any) => p.content || p.raw_text || JSON.stringify(p))
            .join('\n\n---\n\n');
        }
        return parsed.content || parsed.raw_text || JSON.stringify(parsed, null, 2);
      }
      return text;
    } catch {
      return await file.text();
    }
  }

  // 4. Fallback for any other file
  try {
    return await file.text();
  } catch {
    return '';
  }
}
