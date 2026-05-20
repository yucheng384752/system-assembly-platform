import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./ui/table";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { Download, Save, Database, ChevronDown, ChevronUp } from "lucide-react";
import { Progress } from "./ui/progress";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "./ui/alert-dialog";

interface CSVEditorProps {
  fileName: string;
  data: string[][];
  onDataChange: (data: string[][]) => void;
}

export function CSVEditor({ fileName, data, onDataChange }: CSVEditorProps) {
  const { t } = useTranslation();
  const [editedData, setEditedData] = useState<string[][]>(data);
  const [editingCell, setEditingCell] = useState<{ row: number; col: number } | null>(null);
  const [canImport, setCanImport] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importProgress, setImportProgress] = useState(0);
  const [isExpanded, setIsExpanded] = useState(true);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  // Calculate the maximum width for each column
  const columnWidths = useMemo(() => {
    if (!editedData || editedData.length === 0) return [];
    
    const numColumns = editedData[0].length;
    const widths: number[] = [];
    
    for (let col = 0; col < numColumns; col++) {
      let maxLength = 0;
      for (let row = 0; row < editedData.length; row++) {
        const cellContent = editedData[row][col] || '';
        const contentLength = cellContent.length;
        if (contentLength > maxLength) {
          maxLength = contentLength;
        }
      }
      // Calculate width: character count * 8px + padding
      // Minimum width of 150px, maximum width of 400px
      const width = Math.min(Math.max(maxLength * 8 + 40, 150), 400);
      widths.push(width);
    }
    
    return widths;
  }, [editedData]);

  const handleCellChange = (rowIndex: number, colIndex: number, value: string) => {
    const newData = editedData.map((row, rIdx) =>
      rIdx === rowIndex
        ? row.map((cell, cIdx) => (cIdx === colIndex ? value : cell))
        : row
    );
    setEditedData(newData);
  };

  const handleSave = () => {
    onDataChange(editedData);
    setCanImport(true);
    // Use simple notification for now
    console.log("Changes saved");
  };

  const handleImport = async () => {
    setIsImporting(true);
    setImportProgress(0);

    try {
      // TODO: Implement actual API call to backend
      // Legacy import endpoint has been removed; use v2 import jobs commit instead.

      // Simulate import progress
      const totalSteps = 100;
      for (let i = 0; i <= totalSteps; i++) {
        await new Promise((resolve) => setTimeout(resolve, 30));
        setImportProgress(i);
      }

      setIsImporting(false);
      setCanImport(false);
      console.log("Data imported into database");
    } catch (error) {
      console.error('Import failed:', error);
      setIsImporting(false);
    }
  };

  const handleDownload = () => {
    const csvContent = editedData
      .map(row => row.map(cell => {
        // Add quotes if cell contains comma or newline
        if (cell.includes(',') || cell.includes('\n') || cell.includes('"')) {
          return `"${cell.replace(/"/g, '""')}"`;
        }
        return cell;
      }).join(','))
      .join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `edited_${fileName}`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    console.log("CSV downloaded");
  };

  if (!editedData || editedData.length === 0) {
    return null;
  }

  const headers = editedData[0];
  const rows = editedData.slice(1);

  return (
    <div className="bg-white rounded-lg p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-gray-700">{t('csvEditor.titleWithFile', { fileName })}</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsExpanded(!isExpanded)}
            className="flex items-center gap-1"
          >
            {isExpanded ? (
              <>
                <ChevronUp className="w-4 h-4" />
                {t('common.collapse')}
              </>
            ) : (
              <>
                <ChevronDown className="w-4 h-4" />
                {t('common.expand')}
              </>
            )}
          </Button>
        </div>
        <div className="flex gap-2">
          <Button
            onClick={handleDownload}
            variant="outline"
            className="flex items-center gap-2"
            disabled={isImporting}
          >
            <Download className="w-4 h-4" />
            {t('csvEditor.actions.download')}
          </Button>
          <Button
            onClick={handleSave}
            variant="outline"
            className="flex items-center gap-2"
            disabled={isImporting}
          >
            <Save className="w-4 h-4" />
            {t('csvEditor.actions.saveChanges')}
          </Button>
          <Button
            onClick={() => setShowConfirmDialog(true)}
            className="flex items-center gap-2"
            disabled={!canImport || isImporting}
          >
            <Database className="w-4 h-4" />
            {t('csvEditor.actions.confirmImport')}
          </Button>
        </div>
      </div>

      {isImporting && (
        <div className="mb-4 p-4 bg-blue-50 rounded-lg">
          <p className="text-blue-700 mb-2">{t('csvEditor.status.importingWait')}</p>
          <Progress value={importProgress} className="h-2" />
          <p className="text-blue-600 text-sm mt-2">
            {t('csvEditor.status.importProgress', { percent: Math.round(importProgress) })}
          </p>
        </div>
      )}

      {isExpanded && (
        <>
          <div className="border rounded-lg overflow-auto max-h-[500px]">
            <Table>
              <TableHeader>
                <TableRow>
                  {headers.map((_, colIndex) => (
                    <TableHead 
                      key={colIndex} 
                      className="bg-gray-50 font-semibold"
                      style={{ 
                        width: `${columnWidths[colIndex]}px`,
                        minWidth: `${columnWidths[colIndex]}px`,
                        maxWidth: `${columnWidths[colIndex]}px`
                      }}
                    >
                      <Input
                        value={editedData[0][colIndex] || ''}
                        onChange={(e) => handleCellChange(0, colIndex, e.target.value)}
                        className={`border-0 bg-transparent p-1 h-8 w-full font-semibold ${
                          editingCell?.row === 0 && editingCell.col === colIndex
                            ? 'ring-1 ring-blue-500 rounded'
                            : ''
                        }`}
                        onFocus={() => setEditingCell({ row: 0, col: colIndex })}
                        onBlur={() => setEditingCell(null)}
                      />
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((row, rowIndex) => (
                  <TableRow key={rowIndex + 1}>
                    {row.map((_, colIndex) => (
                      <TableCell 
                        key={colIndex}
                        style={{ 
                          width: `${columnWidths[colIndex]}px`,
                          minWidth: `${columnWidths[colIndex]}px`,
                          maxWidth: `${columnWidths[colIndex]}px`
                        }}
                      >
                        <Input
                          value={editedData[rowIndex + 1] && editedData[rowIndex + 1][colIndex] || ''}
                          onChange={(e) => handleCellChange(rowIndex + 1, colIndex, e.target.value)}
                          className={`border-0 hover:border hover:border-blue-300 focus:border-blue-500 p-1 h-8 transition-all w-full ${
                            editingCell?.row === rowIndex + 1 && editingCell.col === colIndex
                              ? 'ring-1 ring-blue-500 rounded'
                              : ''
                          }`}
                          onFocus={() => setEditingCell({ row: rowIndex + 1, col: colIndex })}
                          onBlur={() => setEditingCell(null)}
                        />
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="mt-4 text-gray-500 text-sm">
            <p>{t('csvEditor.footer.summary', { rows: rows.length, cols: headers.length })}</p>
            <p className="mt-1">{t('csvEditor.footer.hint')}</p>
          </div>
        </>
      )}

      <AlertDialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('csvEditor.confirmDialog.title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('csvEditor.confirmDialog.description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                setShowConfirmDialog(false);
                handleImport();
              }}
            >
              {t('common.ok')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}