$loginUrl = "http://127.0.0.1:8080/api/login"
$exportUrl = "http://127.0.0.1:8080/api/workers/export.pdf"
$loginBody = @{
    username = 'superadmin'
    password = '1234'
    loginScope = 'server-admin'
    otpCode = ''
} | ConvertTo-Json

try {
    $loginResp = Invoke-WebRequest -Uri $loginUrl -Method Post -Body $loginBody -ContentType "application/json" -SkipHttpErrorCheck
    Write-Host "Login Status Code: $($loginResp.StatusCode)"
    $loginData = $loginResp.Content | ConvertFrom-Json
    
    if ($loginData.ok -eq $true -and $loginData.token) {
        Write-Host "Token present: True"
        $headers = @{ "Authorization" = "Bearer $($loginData.token)" }
        $exportResp = Invoke-WebRequest -Uri $exportUrl -Headers $headers -Method Get -SkipHttpErrorCheck
        Write-Host "Export Status Code: $($exportResp.StatusCode)"
        Write-Host "Content-Type: $($exportResp.Headers['Content-Type'])"
        if ($exportResp.Content) {
            $bytes = [System.Text.Encoding]::ASCII.GetString($exportResp.Content[0..4])
            Write-Host "First bytes: $bytes"
        }
    } else {
        Write-Host "Login failed: $($loginData.error)"
    }
} catch {
    Write-Host "Error: $($_.Exception.Message)"
}
