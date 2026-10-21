param([string]$In, [string]$OutDocx, [string]$OutPdf)
$w = New-Object -ComObject Word.Application; $w.Visible = $false; $w.DisplayAlerts = 0
try {
  $d = $w.Documents.Open($In)
  [void]$d.Fields.Update()
  foreach ($t in $d.TablesOfContents) { [void]$t.Update() }
  [void]$d.Fields.Update()
  $d.SaveAs2($OutDocx, 16)
  $d.SaveAs2($OutPdf, 17)
  "pages=$($d.ComputeStatistics(2)) words=$($d.ComputeStatistics(0))"
  $d.Close(0)
} finally { $w.Quit() }
