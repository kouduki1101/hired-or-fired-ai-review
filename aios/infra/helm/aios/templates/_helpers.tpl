{{- define "aios.name" -}}
{{- .Chart.Name -}}
{{- end }}

{{- define "aios.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "aios.labels" -}}
app.kubernetes.io/name: {{ include "aios.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "aios.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "aios.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end }}

{{- define "aios.secretName" -}}
{{- if .Values.api.existingSecret -}}
{{- .Values.api.existingSecret -}}
{{- else -}}
{{- include "aios.fullname" . -}}
{{- end -}}
{{- end }}
