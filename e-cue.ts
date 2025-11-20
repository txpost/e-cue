import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from 'fs';
import { createInterface } from 'readline';
import { execSync } from 'child_process';
import { platform } from 'os';
import { program } from 'commander';
import { randomUUID } from 'crypto';
import { join } from 'path';
import ollama from 'ollama';

const MODEL = "llama3:latest";
const ENTRIES_DIR = "entries";

// ANSI color codes
const COLOR_RESET = "\x1b[0m";
const COLOR_USER = "\x1b[96m";  // Bright cyan
const COLOR_E_CUE = "\x1b[92m";  // Bright green


// ==============================
// Spinner animation
// ==============================
class Spinner {
    private static spinnerCycle = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
    private currentIndex = 0;
    private message: string;
    private intervalId: NodeJS.Timeout | null = null;

    constructor(message: string = "Thinking") {
        this.message = message;
    }

    private getNextChar(): string {
        const char = Spinner.spinnerCycle[this.currentIndex];
        this.currentIndex = (this.currentIndex + 1) % Spinner.spinnerCycle.length;
        return char;
    }

    private initSpinner(): void {
        this.intervalId = setInterval(() => {
            process.stdout.write(`\r${this.message} ${this.getNextChar()}`);
        }, 100);
    }

    start(): void {
        this.initSpinner();
    }

    stop(): void {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
        }
        const clearLength = this.message.length + 4;
        process.stdout.write("\r" + " ".repeat(clearLength) + "\r");
    }
}


// ==============================
// File handling
// ==============================
function loadJson<T>(filename: string, defaultValue: T): T {
    try {
        const content = readFileSync(filename, 'utf-8');
        return JSON.parse(content);
    } catch (error) {
        return defaultValue;
    }
}

function saveJson(filename: string, data: any): void {
    writeFileSync(filename, JSON.stringify(data, null, 2));
}

function loadPersona(personaFile: string): string {
    try {
        const content = readFileSync(personaFile, 'utf-8');
        return content.trim();
    } catch (error) {
        console.error(`[error] Persona file '${personaFile}' not found.`);
        process.exit(1);
    }
}

function ensureEntriesDir(): void {
    if (!existsSync(ENTRIES_DIR)) {
        mkdirSync(ENTRIES_DIR, { recursive: true });
    }
}

function saveEntry(entry: EntryFile): void {
    ensureEntriesDir();
    // Format timestamp for filename: replace colons and spaces, keep ISO format
    const timestampPart = entry.timestamp.replace(/[:.]/g, '-').replace('T', '-').replace('Z', '').replace(/-$/, '');
    const filename = `${timestampPart}-${entry.id}.json`;
    const filepath = join(ENTRIES_DIR, filename);
    saveJson(filepath, entry);
}

function loadAllEntries(): EntryFile[] {
    ensureEntriesDir();
    const entries: EntryFile[] = [];

    try {
        const files = readdirSync(ENTRIES_DIR);
        const jsonFiles = files.filter(f => f.endsWith('.json'));

        for (const file of jsonFiles) {
            try {
                const filepath = join(ENTRIES_DIR, file);
                const content = readFileSync(filepath, 'utf-8');
                const entry = JSON.parse(content) as EntryFile;
                entries.push(entry);
            } catch (error) {
                console.error(`[error] Failed to load entry file ${file}: ${error}`);
            }
        }
    } catch (error) {
        // Directory might not exist yet, return empty array
        return [];
    }

    // Sort by timestamp (newest first)
    entries.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
    return entries;
}

function loadEntryById(entryId: string): EntryFile | null {
    ensureEntriesDir();
    try {
        const files = readdirSync(ENTRIES_DIR);
        const jsonFiles = files.filter(f => f.endsWith('.json') && f.includes(entryId));

        if (jsonFiles.length === 0) {
            return null;
        }

        const filepath = join(ENTRIES_DIR, jsonFiles[0]);
        const content = readFileSync(filepath, 'utf-8');
        return JSON.parse(content) as EntryFile;
    } catch (error) {
        return null;
    }
}

function updateEntry(entry: EntryFile): void {
    ensureEntriesDir();
    const timestampPart = entry.timestamp.replace(/[:.]/g, '-').replace('T', '-').replace('Z', '').replace(/-$/, '');
    const filename = `${timestampPart}-${entry.id}.json`;
    const filepath = join(ENTRIES_DIR, filename);
    saveJson(filepath, entry);
}

interface EntryFile {
    id: string;
    timestamp: string;
    content: string;
    word_count: number;
    exchanges: Array<{ user: string; assistant: string }>;
    analysis?: {
        sentiment: string;
        emotions: string[];
        tone: string;
        topics: string[];
        summary: string;
        keywords: string[];
    } | null;
    embedding?: number[] | null;
}

interface JournalEntry {
    timestamp: string;
    persona_file: string;
    word_count: number;
    exchanges: Array<{ user: string; "e-cue": string }>;
}

interface JournalMetadata {
    current_daily_streak: number;
    all_time_daily_streak: number;
    total_word_count: number;
    average_word_count_per_day: number;
    average_word_count_per_session: number;
    total_entries: number;
    last_entry_date: string | null;
}

interface JournalData {
    metadata?: JournalMetadata;
    entries: JournalEntry[];
}

function loadMetadata(): JournalMetadata {
    const defaultMetadata: JournalMetadata = {
        current_daily_streak: 0,
        all_time_daily_streak: 0,
        total_word_count: 0,
        average_word_count_per_day: 0,
        average_word_count_per_session: 0,
        total_entries: 0,
        last_entry_date: null,
    };

    const metadata = loadJson<JournalMetadata>("metadata.json", defaultMetadata);

    // Calculate metadata from all entries
    const entries = loadAllEntries();
    if (entries.length > 0) {
        return calculateMetadata(entries);
    }

    return metadata;
}

function saveMetadata(metadata: JournalMetadata): void {
    saveJson("metadata.json", metadata);
}

function calculateMetadata(entries: EntryFile[]): JournalMetadata {
    if (entries.length === 0) {
        return {
            current_daily_streak: 0,
            all_time_daily_streak: 0,
            total_word_count: 0,
            average_word_count_per_day: 0,
            average_word_count_per_session: 0,
            total_entries: 0,
            last_entry_date: null,
        };
    }

    const MIN_WORDS_FOR_STREAK = 750;

    // Calculate total word count and track dates with qualifying sessions (750+ words)
    let totalWordCount = 0;
    const dates = new Set<string>();
    const qualifyingDates = new Set<string>(); // Dates with at least one 750+ word session
    const dateWordCounts = new Map<string, number>(); // Track total words per day
    let lastEntryDate: string | null = null;

    for (const entry of entries) {
        const wordCount = entry.word_count || 0;
        totalWordCount += wordCount;

        // Extract date from timestamp (ISO format: "2025-11-18T13:58:26Z")
        const dateStr = entry.timestamp.split('T')[0];
        dates.add(dateStr);

        // Track total words per day
        dateWordCounts.set(dateStr, (dateWordCounts.get(dateStr) || 0) + wordCount);

        // Track dates with at least one qualifying session (750+ words)
        if (wordCount >= MIN_WORDS_FOR_STREAK) {
            qualifyingDates.add(dateStr);
        }

        // Track most recent entry date
        if (!lastEntryDate || entry.timestamp > lastEntryDate) {
            lastEntryDate = dateStr;
        }
    }

    // Calculate averages
    const averageWordCountPerSession = totalWordCount / entries.length;
    const uniqueDaysCount = dates.size;
    const averageWordCountPerDay = uniqueDaysCount > 0 ? totalWordCount / uniqueDaysCount : 0;

    // Sort qualifying dates for streak calculation
    const sortedQualifyingDates = Array.from(qualifyingDates).sort();

    // Calculate current daily streak (consecutive days ending today with 750+ word session)
    const today = new Date();
    const todayStr = today.toISOString().split('T')[0];

    let currentStreak = 0;
    // Only count streak if there's a qualifying entry today
    if (qualifyingDates.has(todayStr)) {
        // Check backwards from today
        const checkDate = new Date(today);
        let streakDate = todayStr;

        while (qualifyingDates.has(streakDate)) {
            currentStreak++;
            checkDate.setDate(checkDate.getDate() - 1);
            streakDate = checkDate.toISOString().split('T')[0];
        }
    }

    // Calculate all-time daily streak (longest consecutive period with 750+ word sessions)
    let allTimeStreak = 0;
    if (sortedQualifyingDates.length > 0) {
        let maxStreak = 1;
        let currentConsecutive = 1;

        for (let i = 1; i < sortedQualifyingDates.length; i++) {
            const prevDate = new Date(sortedQualifyingDates[i - 1]);
            const currDate = new Date(sortedQualifyingDates[i]);
            const diffDays = Math.floor((currDate.getTime() - prevDate.getTime()) / (1000 * 60 * 60 * 24));

            if (diffDays === 1) {
                // Consecutive day
                currentConsecutive++;
                maxStreak = Math.max(maxStreak, currentConsecutive);
            } else {
                // Gap found, reset counter
                currentConsecutive = 1;
            }
        }

        allTimeStreak = maxStreak;
    }

    return {
        current_daily_streak: currentStreak,
        all_time_daily_streak: allTimeStreak,
        total_word_count: totalWordCount,
        average_word_count_per_day: Math.round(averageWordCountPerDay * 100) / 100, // Round to 2 decimal places
        average_word_count_per_session: Math.round(averageWordCountPerSession * 100) / 100, // Round to 2 decimal places
        total_entries: entries.length,
        last_entry_date: lastEntryDate,
    };
}

function countWords(text: string): number {
    /** Count words in a text string. */
    return text.trim() ? text.split(/\s+/).length : 0;
}

async function generateAnalysis(content: string): Promise<{
    sentiment: string;
    emotions: string[];
    tone: string;
    topics: string[];
    summary: string;
    keywords: string[];
}> {
    const analysisPrompt = `Analyze the following journal entry and provide a structured analysis in JSON format with the following fields:
- sentiment: one word describing overall sentiment (e.g., "positive", "negative", "mixed", "neutral")
- emotions: array of 2-5 emotion words (e.g., ["happy", "anxious", "hopeful"])
- tone: one word describing the writing tone (e.g., "reflective", "energetic", "melancholic", "optimistic")
- topics: array of 3-7 main topics or themes (e.g., ["work", "relationships", "health"])
- summary: a brief 1-2 sentence summary of the entry
- keywords: array of 5-10 important keywords or phrases

Journal entry:
${content}

Respond with ONLY valid JSON in this exact format:
{
  "sentiment": "...",
  "emotions": [...],
  "tone": "...",
  "topics": [...],
  "summary": "...",
  "keywords": [...]
}`;

    try {
        const response = await ollama.chat({
            model: MODEL,
            messages: [{ role: "user", content: analysisPrompt }],
        });

        const responseText = response.message.content.trim();
        // Try to extract JSON from the response (in case there's extra text)
        const jsonMatch = responseText.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
            const analysis = JSON.parse(jsonMatch[0]);
            return {
                sentiment: analysis.sentiment || "neutral",
                emotions: Array.isArray(analysis.emotions) ? analysis.emotions : [],
                tone: analysis.tone || "neutral",
                topics: Array.isArray(analysis.topics) ? analysis.topics : [],
                summary: analysis.summary || "",
                keywords: Array.isArray(analysis.keywords) ? analysis.keywords : [],
            };
        }
        throw new Error("No JSON found in response");
    } catch (error) {
        console.error(`[error] Failed to generate analysis: ${error}`);
        // Return default analysis on error
        return {
            sentiment: "neutral",
            emotions: [],
            tone: "neutral",
            topics: [],
            summary: "",
            keywords: [],
        };
    }
}

async function generateEmbedding(content: string): Promise<number[]> {
    try {
        const response = await ollama.embeddings({
            model: MODEL,
            prompt: content,
        });
        return response.embedding;
    } catch (error) {
        console.error(`[error] Failed to generate embedding: ${error}`);
        return [];
    }
}

async function enrichEntry(entryId: string): Promise<void> {
    const entry = loadEntryById(entryId);
    if (!entry) {
        console.error(`[error] Entry with ID ${entryId} not found.`);
        return;
    }

    // Skip if already enriched
    if (entry.analysis && entry.embedding) {
        console.log(`Entry ${entryId} already has analysis and embedding.`);
        return;
    }

    console.log(`Generating analysis and embedding for entry ${entryId}...`);
    const spinner = new Spinner("Processing");
    spinner.start();

    try {
        // Generate analysis if missing
        if (!entry.analysis) {
            entry.analysis = await generateAnalysis(entry.content);
        }

        // Generate embedding if missing
        if (!entry.embedding || entry.embedding.length === 0) {
            entry.embedding = await generateEmbedding(entry.content);
        }

        // Update entry file
        updateEntry(entry);
        spinner.stop();
        console.log(`${COLOR_E_CUE}✓ Successfully enriched entry ${entryId}.${COLOR_RESET}`);
    } catch (error) {
        spinner.stop();
        console.error(`[error] Failed to enrich entry: ${error}`);
    }
}

async function enrichAllEntries(): Promise<void> {
    const entries = loadAllEntries();
    const entriesToEnrich = entries.filter(e => !e.analysis || !e.embedding || e.embedding.length === 0);

    if (entriesToEnrich.length === 0) {
        console.log("All entries are already enriched.");
        return;
    }

    console.log(`Found ${entriesToEnrich.length} entries to enrich.`);

    for (const entry of entriesToEnrich) {
        await enrichEntry(entry.id);
    }

    console.log(`${COLOR_E_CUE}✓ Finished enriching all entries.${COLOR_RESET}`);
}


// ==============================
// Main journaling loop
// ==============================
async function journalLoop(personaFile: string): Promise<void> {
    // Clear the terminal screen
    const clearCommand = platform() === 'win32' ? 'cls' : 'clear';
    execSync(clearCommand, { stdio: 'inherit' });

    const persona = loadPersona(personaFile);

    const systemPrompt = persona;
    const messages: Array<{ role: string; content: string }> = [
        { role: "system", content: systemPrompt }
    ];

    console.log(`Journaling with persona: ${personaFile}`);
    console.log("Type 'save' to save and exit, or 'exit'/'quit' to end without saving.\n");

    let cumulativeWords = 0;
    const sessionStartTime = new Date();
    const sessionExchanges: Array<{ user: string; assistant: string }> = [];

    const rl = createInterface({
        input: process.stdin,
        output: process.stdout,
    });

    const question = (prompt: string): Promise<string> => {
        return new Promise((resolve) => {
            rl.question(prompt, resolve);
        });
    };

    while (true) {
        const userInput = (await question(`${COLOR_USER}You:${COLOR_RESET} `)).trim();
        if (!userInput) {
            continue;
        }
        if (userInput.toLowerCase() === "exit" || userInput.toLowerCase() === "quit") {
            console.log("\nEnding journal session (not saved).");
            break;
        }
        if (userInput.toLowerCase() === "save") {
            // Save session as a single entry
            if (sessionExchanges.length > 0) {
                // Concatenate all user inputs into content field
                const content = sessionExchanges.map(ex => ex.user).join(' ');

                const entryId = randomUUID();
                const timestamp = sessionStartTime.toISOString();

                const entry: EntryFile = {
                    id: entryId,
                    timestamp: timestamp,
                    content: content,
                    word_count: cumulativeWords,
                    exchanges: sessionExchanges,
                    analysis: null,
                    embedding: null,
                };

                saveEntry(entry);

                // Calculate and update metadata
                const allEntries = loadAllEntries();
                const metadata = calculateMetadata(allEntries);
                saveMetadata(metadata);

                console.log(`\n${COLOR_E_CUE}✓ Saved session with ${sessionExchanges.length} exchanges to entry ${entryId}.${COLOR_RESET}\n`);
            } else {
                console.log(`\n${COLOR_E_CUE}No entries to save.${COLOR_RESET}\n`);
            }
            console.log("Ending journal session.");
            break;
        }

        // Show cumulative word count after input
        const wordCount = countWords(userInput);
        cumulativeWords += wordCount;
        console.log(`${COLOR_USER}[${wordCount} words this entry, ${cumulativeWords} words total]${COLOR_RESET}`);

        messages.push({ role: "user", content: userInput });

        const spinner = new Spinner();
        spinner.start();
        try {
            const response = await ollama.chat({
                model: MODEL,
                messages: messages as any,
            });
            spinner.stop();

            const aiMessage = response.message.content.trim();
            console.log(`\n${COLOR_E_CUE}e-cue:${COLOR_RESET} ${aiMessage}\n`);
            messages.push({ role: "e-cue", content: aiMessage });

            // Store exchange in session (not saved yet)
            const exchange = {
                user: userInput,
                assistant: aiMessage,
            };
            sessionExchanges.push(exchange);
        } catch (e: any) {
            spinner.stop();
            console.error(`\n[error] ${e}`);
            continue;
        }
    }

    rl.close();
}

async function main(): Promise<void> {
    const args = process.argv.slice(2);
    const hasCommand = args.some(arg => arg === "enrich" || arg === "enrich-all" || arg === "help");

    // If no command, manually parse persona option and run journal loop
    if (!hasCommand) {
        let personaFile = "persona.txt";
        const personaIndex = args.indexOf("--persona");
        if (personaIndex !== -1 && args[personaIndex + 1]) {
            personaFile = args[personaIndex + 1];
        }
        await journalLoop(personaFile);
        return;
    }

    program
        .description("Journal with different personas")
        .option(
            "--persona <path>",
            "Path to persona file (default: persona.txt)",
            "persona.txt"
        );

    program
        .command("enrich")
        .description("Generate analysis and embedding for an entry")
        .argument("<entry-id>", "Entry ID to enrich")
        .action(async (entryId: string) => {
            await enrichEntry(entryId);
            process.exit(0);
        });

    program
        .command("enrich-all")
        .description("Generate analysis and embedding for all entries that need it")
        .action(async () => {
            await enrichAllEntries();
            process.exit(0);
        });

    program.parse();
}

if (require.main === module) {
    main().catch((error) => {
        console.error("Fatal error:", error);
        process.exit(1);
    });
}

