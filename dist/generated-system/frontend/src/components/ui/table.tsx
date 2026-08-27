import type { ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react"
export function Table({ children }: { children?: ReactNode }) { return <table style={{ width:"100%",borderCollapse:"collapse" }}>{children}</table> }
export function TableHeader({ children }: { children?: ReactNode }) { return <thead>{children}</thead> }
export function TableBody({ children }: { children?: ReactNode }) { return <tbody>{children}</tbody> }
export function TableRow({ children }: { children?: ReactNode }) { return <tr>{children}</tr> }
export function TableHead({ children, ...p }: ThHTMLAttributes<HTMLTableCellElement>) { return <th style={{ padding:"8px",borderBottom:"1px solid #e5e7eb",textAlign:"left" }} {...p}>{children}</th> }
export function TableCell({ children, ...p }: TdHTMLAttributes<HTMLTableCellElement>) { return <td style={{ padding:"8px",borderBottom:"1px solid #e5e7eb" }} {...p}>{children}</td> }