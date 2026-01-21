import { readFileSync } from 'fs';
import { extname } from 'path';

type TextChunks = Record<string, string>;

type CardData = Record<string, any>;

type ParsedCard = {
  name: string;
  description: string;
  personality: string;
  scenario: string;
  first_mes: string;
  mes_example: string;
  system_prompt: string;
  post_history_instructions: string;
  alternate_greetings: string[];
  creator_notes: string;
  tags: string[];
  creator: string;
  character_version: string;
  character_book: any;
  extensions: Record<string, any>;
  nickname: string;
  source: string[];
  group_only_greetings: string[];
  assets: any[];
  creator_notes_multilingual: Record<string, any>;
  creation_date: any;
  modification_date: any;
  _version: string;
  _spec: string;
  _spec_version: string;
};

const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function readPngTextChunks(filepath: string): TextChunks {
  const data = readFileSync(filepath);
  if (data.length < 8 || !data.subarray(0, 8).equals(PNG_SIGNATURE)) {
    throw new Error('Not a valid PNG file');
  }

  const textChunks: TextChunks = {};
  let offset = 8;

  while (offset + 8 <= data.length) {
    const length = data.readUInt32BE(offset);
    const type = data.toString('ascii', offset + 4, offset + 8);
    const dataStart = offset + 8;
    const dataEnd = dataStart + length;
    const crcEnd = dataEnd + 4;

    if (crcEnd > data.length) {
      break;
    }

    const chunkData = data.subarray(dataStart, dataEnd);

    if (type === 'tEXt' && chunkData.length > 0) {
      const nullIdx = chunkData.indexOf(0x00);
      if (nullIdx !== -1) {
        const keyword = chunkData.subarray(0, nullIdx).toString('latin1');
        const value = chunkData.subarray(nullIdx + 1).toString('latin1');
        textChunks[keyword.toLowerCase()] = value;
      }
    } else if (type === 'iTXt' && chunkData.length > 0) {
      const nullIdx = chunkData.indexOf(0x00);
      if (nullIdx !== -1) {
        const keyword = chunkData.subarray(0, nullIdx).toString('utf8');
        let rest = chunkData.subarray(nullIdx + 1);
        if (rest.length > 2) {
          rest = rest.subarray(2);
          const langEnd = rest.indexOf(0x00);
          if (langEnd !== -1) {
            rest = rest.subarray(langEnd + 1);
            const transEnd = rest.indexOf(0x00);
            if (transEnd !== -1) {
              const value = rest.subarray(transEnd + 1).toString('utf8');
              textChunks[keyword.toLowerCase()] = value;
            }
          }
        }
      }
    }

    if (type === 'IEND') {
      break;
    }

    offset = crcEnd;
  }

  return textChunks;
}

function extractCharacterJson(filepath: string): CardData | null {
  const textChunks = readPngTextChunks(filepath);
  const charaData = textChunks.chara;
  if (!charaData) return null;

  const padded = (() => {
    const remainder = charaData.length % 4;
    if (remainder === 0) return charaData;
    return `${charaData}${'='.repeat(4 - remainder)}`;
  })();

  try {
    const jsonStr = Buffer.from(padded, 'base64').toString('utf8');
    return JSON.parse(jsonStr);
  } catch {
    try {
      const jsonStr = Buffer.from(charaData, 'base64').toString('utf8');
      return JSON.parse(jsonStr);
    } catch {
      return null;
    }
  }
}

function detectVersion(raw: CardData): string {
  const spec = raw?.spec ?? '';
  if (spec === 'chara_card_v3') return 'v3';
  if (spec === 'chara_card_v2') return 'v2';
  return 'v1';
}

function getStr(data: CardData, key: string, defaultValue = ''): string {
  const value = data?.[key];
  if (value === undefined || value === null) return defaultValue;
  return typeof value === 'string' ? value : String(value);
}

function getList(data: CardData, key: string): any[] {
  const value = data?.[key];
  if (value === undefined || value === null) return [];
  if (Array.isArray(value)) return value;
  return [value];
}

export function parseCard(filepath: string): ParsedCard {
  const ext = extname(filepath).toLowerCase();
  let raw: CardData | null = null;

  if (ext === '.png' || ext === '.apng') {
    raw = extractCharacterJson(filepath);
    if (!raw) {
      throw new Error(`No character data found in ${filepath}`);
    }
  } else if (ext === '.json') {
    raw = JSON.parse(readFileSync(filepath, 'utf8')) as CardData;
  } else {
    try {
      raw = JSON.parse(readFileSync(filepath, 'utf8')) as CardData;
    } catch {
      throw new Error(`Unsupported file type: ${ext || '(unknown)'}`);
    }
  }

  if (!raw) {
    throw new Error('Empty character data');
  }

  const version = detectVersion(raw);
  let data: CardData = raw;
  if (version === 'v2' || version === 'v3') {
    data = raw.data && Object.keys(raw.data).length ? raw.data : raw;
  }

  const result: ParsedCard = {
    name: getStr(data, 'name', 'Unknown'),
    description: getStr(data, 'description'),
    personality: getStr(data, 'personality'),
    scenario: getStr(data, 'scenario'),
    first_mes: getStr(data, 'first_mes'),
    mes_example: getStr(data, 'mes_example'),
    system_prompt: getStr(data, 'system_prompt'),
    post_history_instructions: getStr(data, 'post_history_instructions'),
    alternate_greetings: getList(data, 'alternate_greetings') as string[],
    creator_notes: getStr(data, 'creator_notes'),
    tags: getList(data, 'tags') as string[],
    creator: getStr(data, 'creator'),
    character_version: getStr(data, 'character_version'),
    character_book: data.character_book,
    extensions: (data.extensions ?? {}) as Record<string, any>,
    nickname: getStr(data, 'nickname'),
    source: getList(data, 'source') as string[],
    group_only_greetings: getList(data, 'group_only_greetings') as string[],
    assets: (data.assets ?? []) as any[],
    creator_notes_multilingual: (data.creator_notes_multilingual ?? {}) as Record<string, any>,
    creation_date: data.creation_date,
    modification_date: data.modification_date,
    _version: version,
    _spec: raw.spec ?? 'v1',
    _spec_version: raw.spec_version ?? '1.0',
  };

  return result;
}
