import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'

export async function exportReportToPdf({ elementId = 'pdf-report-root', fileName = 'CodeEval-AI-Report.pdf', onProgress }) {
  const container = document.getElementById(elementId)
  if (!container) {
    throw new Error('PDF Report template container not found.')
  }

  if (onProgress) onProgress('Capturing report sections...')

  const pages = container.querySelectorAll('.pdf-page')
  const pdf = new jsPDF({
    orientation: 'portrait',
    unit: 'mm',
    format: 'a4',
  })

  const pdfWidth = pdf.internal.pageSize.getWidth() // 210 mm
  const pdfHeight = pdf.internal.pageSize.getHeight() // 297 mm

  for (let i = 0; i < pages.length; i++) {
    const pageEl = pages[i]
    if (onProgress) onProgress(`Processing section ${i + 1} of ${pages.length}...`)

    const canvas = await html2canvas(pageEl, {
      scale: 2,
      useCORS: true,
      backgroundColor: '#0b0f12',
      logging: false,
    })

    const imgData = canvas.toDataURL('image/png')

    if (i > 0) {
      pdf.addPage()
    }

    pdf.addImage(imgData, 'PNG', 0, 0, pdfWidth, pdfHeight)

    // Add footer to page
    pdf.setTextColor(156, 163, 175)
    pdf.setFontSize(8)
    pdf.text(`CodeEval AI Enterprise Report — Page ${i + 1} of ${pages.length}`, 10, pdfHeight - 6)
  }

  if (onProgress) onProgress('Finalizing PDF document...')
  pdf.save(fileName)
}
