{{- define "baupass.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "baupass.fullname" -}}
{{- printf "%s-%s" .Release.Name (include "baupass.name" .) | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "baupass.labels" -}}
app.kubernetes.io/name: {{ include "baupass.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}
