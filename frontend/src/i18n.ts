export type UiLanguage="es"|"en";

export function uiLanguage(code?:string):UiLanguage{
  return code?.toLowerCase().startsWith("es")?"es":"en";
}

export function uiCopy(language:UiLanguage,spanish:string,english:string):string{
  return language==="es"?spanish:english;
}
