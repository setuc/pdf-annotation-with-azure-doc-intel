// src/lib/utils.ts
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'
// Remove or modify the warning import if it exists

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
