export function toValidateProgress(jobStatus: string): number {
  switch (jobStatus) {
    case "UPLOADED":
      return 25;
    case "PARSING":
      return 45;
    case "VALIDATING":
      return 75;
    case "READY":
    case "FAILED":
      return 100;
    default:
      return 30;
  }
}

export function toImportProgress(jobStatus: string): number {
  switch (jobStatus) {
    case "COMMITTING":
      return 60;
    case "COMPLETED":
    case "FAILED":
      return 100;
    default:
      return 30;
  }
}

export function toPdfConvertProgress(convertStatus: string): number {
  switch (convertStatus) {
    case "NOT_STARTED":
      return 0;
    case "QUEUED":
      return 10;
    case "UPLOADING":
      return 25;
    case "PROCESSING":
      return 65;
    case "COMPLETED":
    case "FAILED":
      return 100;
    default:
      return 30;
  }
}
