/*
Copyright 2017 - 2017 Amazon.com, Inc. or its affiliates. All Rights Reserved.
Licensed under the Apache License, Version 2.0 (the "License"). You may not use this file except in compliance with the License. A copy of the License is located at
    http://aws.amazon.com/apache2.0/
or in the "license" file accompanying this file. This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and limitations under the License.
*/



const { DynamoDBClient } = require('@aws-sdk/client-dynamodb');
const { DeleteCommand, DynamoDBDocumentClient, GetCommand, PutCommand, QueryCommand, ScanCommand, UpdateCommand } = require('@aws-sdk/lib-dynamodb');
const { SESClient, SendEmailCommand } = require('@aws-sdk/client-ses');
const PDFDocument = require('pdfkit');
const fetch = require('node-fetch');
const fs = require('fs');
const awsServerlessExpressMiddleware = require('aws-serverless-express/middleware')
const bodyParser = require('body-parser')
const express = require('express')
const { randomUUID } = require('crypto');

const ddbClient = new DynamoDBClient({ region: process.env.TABLE_REGION || process.env.REGION || 'us-east-2' });
const ddbDocClient = DynamoDBDocumentClient.from(ddbClient, {
  marshallOptions: { convertEmptyValues: true, removeUndefinedValues: true },
  unmarshallOptions: { wrapNumbers: false }
});

// Initialize SES client
const sesClient = new SESClient({ region: process.env.TABLE_REGION || process.env.REGION || 'us-east-2' });

let tableName = "WaitList";
if (process.env.ENV && process.env.ENV !== "NONE") {
  tableName = tableName + '-' + process.env.ENV;
}

// Debug configuration at startup
console.log('WaitList API config:', {
  region: process.env.TABLE_REGION || process.env.REGION || 'us-east-2',
  tableName,
  env: process.env.ENV || 'NONE'
});

const userIdPresent = false; // TODO: update in case is required to use that definition
const partitionKeyName = "id";
const partitionKeyType = "S";
const sortKeyName = "";
const sortKeyType = "";
const hasSortKey = sortKeyName !== "";
const path = "/waitlist";
const calcPath = "/calculator";
const feeComparisonPath = "/fee-comparison";
const listingOptimizerPath = "/listing-optimizer";
const ratingPath = "/rating";
const UNAUTH = 'UNAUTH';
const hashKeyPath = '/:' + partitionKeyName;
const sortKeyPath = hasSortKey ? '/:' + sortKeyName : '';

// declare a new express app
const app = express()
app.use(bodyParser.json())
app.use(awsServerlessExpressMiddleware.eventContext())

// Enable CORS for all methods
app.use(function(req, res, next) {
  res.header("Access-Control-Allow-Origin", "*")
  res.header("Access-Control-Allow-Headers", "*")
  res.header("Access-Control-Allow-Methods", "OPTIONS,POST,GET")
  next()
});

// Add debug middleware to log all requests
app.use(function(req, res, next) {
  console.log('=== REQUEST DEBUG ===');
  console.log('Method:', req.method);
  console.log('URL:', req.url);
  console.log('Path:', req.path);
  console.log('Query:', req.query);
  console.log('Headers:', JSON.stringify(req.headers, null, 2));
  console.log('===================');
  next();
});

/************************************
* HTTP Get method for Gemini config *
************************************/

// Gemini config route - handle multiple possible paths
app.get('/gemini-config', handleGeminiConfig);
app.get('/waitlist/gemini-config', handleGeminiConfig);
function sendPreflightOk(res) {
  res.header("Access-Control-Allow-Origin", "*");
  res.header("Access-Control-Allow-Headers", "*");
  res.header("Access-Control-Allow-Methods", "OPTIONS,POST,GET");
  res.status(200).send();
}

app.options(calcPath, (req, res) => {
  sendPreflightOk(res);
});
app.options(path + calcPath, (req, res) => {
  sendPreflightOk(res);
});
app.options(feeComparisonPath, (req, res) => {
  sendPreflightOk(res);
});
app.options(path + feeComparisonPath, (req, res) => {
  sendPreflightOk(res);
});
app.options(listingOptimizerPath, (req, res) => sendPreflightOk(res));
app.options(path + listingOptimizerPath, (req, res) => sendPreflightOk(res));
app.options(ratingPath, (req, res) => sendPreflightOk(res));
app.options(path + ratingPath, (req, res) => sendPreflightOk(res));

// Preflight for base waitlist path
app.options(path, (req, res) => sendPreflightOk(res));

function handleGeminiConfig(req, res) {
  console.log('=== GEMINI CONFIG ENDPOINT HIT ===');
  console.log('Request path:', req.path);
  console.log('Request URL:', req.url);
  console.log('Environment GEMINI_API_KEY exists:', !!process.env.GEMINI_API_KEY);
  
  // Return Gemini API key securely from environment variables
  const geminiApiKey = process.env.GEMINI_API_KEY;
  
  if (!geminiApiKey) {
    console.error("Gemini API key not configured in Lambda environment");
    res.statusCode = 500;
    res.json({ 
      error: "API key not configured",
      message: "Voice call functionality is currently unavailable"
    });
    return;
  }
  
  console.log('Returning API key, length:', geminiApiKey.length);
  // Return the API key securely
  res.json({
    apiKey: geminiApiKey
  });
}

// convert url string param to expected Type
const convertUrlType = (param, type) => {
  switch(type) {
    case "N":
      return Number.parseInt(param);
    default:
      return param;
  }
}

/************************************
* HTTP Get method to list objects *
************************************/

app.get(path, async function(req, res) {
  var params = {
    TableName: tableName,
    Select: 'ALL_ATTRIBUTES',
  };

  try {
    const data = await ddbDocClient.send(new ScanCommand(params));
    res.json(data.Items);
  } catch (err) {
    res.statusCode = 500;
    res.json({error: 'Could not load items: ' + err.message});
  }
});

/************************************
 * HTTP Get method to query objects *
 ************************************/

app.get(path + hashKeyPath, async function(req, res) {
  const condition = {}
  condition[partitionKeyName] = {
    ComparisonOperator: 'EQ'
  }

  if (userIdPresent && req.apiGateway) {
    condition[partitionKeyName]['AttributeValueList'] = [req.apiGateway.event.requestContext.identity.cognitoIdentityId || UNAUTH ];
  } else {
    try {
      condition[partitionKeyName]['AttributeValueList'] = [ convertUrlType(req.params[partitionKeyName], partitionKeyType) ];
    } catch(err) {
      res.statusCode = 500;
      res.json({error: 'Wrong column type ' + err});
    }
  }

  let queryParams = {
    TableName: tableName,
    KeyConditions: condition
  }

  try {
    const data = await ddbDocClient.send(new QueryCommand(queryParams));
    res.json(data.Items);
  } catch (err) {
    res.statusCode = 500;
    res.json({error: 'Could not load items: ' + err.message});
  }
});

/*****************************************
 * HTTP Get method for get single object *
 *****************************************/

app.get(path + '/object' + hashKeyPath + sortKeyPath, async function(req, res) {
  const params = {};
  if (userIdPresent && req.apiGateway) {
    params[partitionKeyName] = req.apiGateway.event.requestContext.identity.cognitoIdentityId || UNAUTH;
  } else {
    params[partitionKeyName] = req.params[partitionKeyName];
    try {
      params[partitionKeyName] = convertUrlType(req.params[partitionKeyName], partitionKeyType);
    } catch(err) {
      res.statusCode = 500;
      res.json({error: 'Wrong column type ' + err});
    }
  }
  if (hasSortKey) {
    try {
      params[sortKeyName] = convertUrlType(req.params[sortKeyName], sortKeyType);
    } catch(err) {
      res.statusCode = 500;
      res.json({error: 'Wrong column type ' + err});
    }
  }

  let getItemParams = {
    TableName: tableName,
    Key: params
  }

  try {
    const data = await ddbDocClient.send(new GetCommand(getItemParams));
    if (data.Item) {
      res.json(data.Item);
    } else {
      res.json(data) ;
    }
  } catch (err) {
    res.statusCode = 500;
    res.json({error: 'Could not load items: ' + err.message});
  }
});


/************************************
* HTTP put method for insert object *
*************************************/

app.put(path, async function(req, res) {

  if (userIdPresent) {
    req.body['userId'] = req.apiGateway.event.requestContext.identity.cognitoIdentityId || UNAUTH;
  }

  let putItemParams = {
    TableName: tableName,
    Item: req.body
  }
  try {
    let data = await ddbDocClient.send(new PutCommand(putItemParams));
    res.json({ success: 'put call succeed!', url: req.url, data: data })
  } catch (err) {
    res.statusCode = 500;
    res.json({ error: err, url: req.url, body: req.body });
  }
});

// Email validation function
function isValidEmail(email) {
  const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  return emailRegex.test(email);
}

// Function to send email notification
async function sendEmailNotification(firstName, lastName, email, message) {
  const emailSubject = `New Contact Form Submission from ${firstName} ${lastName}`;

  // Format timestamp in a user-friendly way
  const now = new Date();
  const formattedDate = now.toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric'
  });
  const formattedTime = now.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short'
  });

  const emailBody = `
New contact form submission from Guestrix website:

Name: ${firstName} ${lastName}
Email: ${email}
Message: ${message || 'No message provided'}

Submitted at: ${formattedDate} at ${formattedTime}
  `.trim();

  const params = {
    Destination: {
      ToAddresses: ['hello@guestrix.ai']
    },
    Message: {
      Body: {
        Text: {
          Data: emailBody,
          Charset: 'UTF-8'
        }
      },
      Subject: {
        Data: emailSubject,
        Charset: 'UTF-8'
      }
    },
    Source: 'hello@guestrix.ai', // Must be verified in SES
    ReplyToAddresses: [email]
  };

  try {
    // Lightweight debug for SES send context
    console.log('SES send context:', {
      region: process.env.TABLE_REGION || process.env.REGION || 'us-east-2',
      source: params.Source,
      to: params.Destination?.ToAddresses,
      replyTo: params.ReplyToAddresses
    });
    const result = await sesClient.send(new SendEmailCommand(params));
    console.log('Email sent successfully:', result.MessageId);
    return { success: true, messageId: result.MessageId };
  } catch (error) {
    console.error('Error sending email:', error);
    return { success: false, error: error.message };
  }
}
// Helper: call Gemini with web search tool to produce structured output
async function fetchZipInsights(zipCode) {
  const defaults = {
    city: 'Unknown',
    adr: { High: 220, Shoulder: 180, Low: 140, Holiday: 260, Event: 300 },
    occupancy: 65
  };
  let apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    // Attempt to read from a local .env packaged with the function (for dev fallback)
    try {
      const envText = fs.readFileSync(__dirname + '/.env', 'utf8');
      const match = envText.split(/\r?\n/).find((l) => l.trim().startsWith('GEMINI_API_KEY='));
      if (match) {
        apiKey = match.split('=')[1].trim();
        console.log('Loaded GEMINI_API_KEY from .env fallback');
      }
    } catch (e) {
      // ignore
    }
  }
  if (!apiKey) {
    console.error('GEMINI_API_KEY missing, using defaults');
    return defaults;
  }

  // Compose prompt asking Gemini for city/area, ADRs per season, occupancy
  const prompt = `You are a data assistant. Given US ZIP code ${zipCode}, use reputable web sources to estimate short-term rental metrics specific to that ZIP's primary city/area. Return ONLY compact JSON with this exact shape:
{
  "city": "City, ST",
  "adr": { "High": 0, "Shoulder": 0, "Low": 0, "Holiday": 0, "Event": 0 },
  "occupancy": 0
}
Where adr values are integers in USD (average nightly price) per season and occupancy is an integer percent between 40 and 90. Ensure values are ZIP-specific (or the most local area covered by data). No commentary.`;

  // Use Gemini 2.5 Flash-Lite with web access and retry logic for rate limits
  const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=' + encodeURIComponent(apiKey);
  const body = {
    contents: [
      {
        role: 'user',
        parts: [
          { text: prompt }
        ]
      }
    ],
    tools: [ { googleSearch: {} } ]
  };

  // Retry logic for rate limits
  const maxRetries = 3;
  let resp;
  let lastError;
  
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      console.log(`Gemini API attempt ${attempt}/${maxRetries} for ZIP ${zipCode}`);
      resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      
      if (resp.status === 429) {
        // Rate limited - wait and retry
        const retryAfter = resp.headers.get('retry-after') || 30;
        console.log(`Rate limited, waiting ${retryAfter} seconds before retry...`);
        await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
        lastError = `Rate limited (attempt ${attempt})`;
        continue;
      }
      
      if (!resp.ok) {
        const errText = await resp.text().catch(() => '');
        console.error(`Gemini API error (attempt ${attempt}):`, errText);
        lastError = errText;
        if (attempt === maxRetries) {
          console.error('All retries exhausted, using defaults');
          return defaults;
        }
        // Wait before retry for other errors
        await new Promise(resolve => setTimeout(resolve, 2000));
        continue;
      }
      
      // Success - break out of retry loop
      break;
      
    } catch (err) {
      console.error(`Gemini API request failed (attempt ${attempt}):`, err?.message || err);
      lastError = err?.message || err;
      if (attempt === maxRetries) {
        console.error('All retries exhausted, using defaults');
        return defaults;
      }
      // Wait before retry
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
  }
  const data = await resp.json().catch(() => ({}));
  // Try multiple Gemini response shapes
  let text = data?.candidates?.[0]?.content?.parts?.[0]?.text || '';
  if (!text && Array.isArray(data?.candidates) && data.candidates[0]?.output_text) {
    text = data.candidates[0].output_text;
  }
  // Handle markdown code blocks in Gemini response
  let jsonText = text.trim();
  if (jsonText.startsWith('```json')) {
    jsonText = jsonText.replace(/^```json\s*/, '').replace(/\s*```$/, '');
  } else if (jsonText.startsWith('```')) {
    jsonText = jsonText.replace(/^```\s*/, '').replace(/\s*```$/, '');
  }
  
  let parsed;
  try {
    parsed = JSON.parse(jsonText);
  } catch (e) {
    parsed = defaults;
  }
  // Normalize
  const adr = parsed.adr || defaults.adr;
  const occupancy = Number(parsed.occupancy) || defaults.occupancy;
  let city = typeof parsed.city === 'string' && parsed.city.trim() ? parsed.city.trim() : defaults.city;
  // Always attempt a reliable city from ZIP; prefer lookup result
  try {
    const loc = await lookupCityFromZip(zipCode);
    if (loc) city = loc;
  } catch (e) {
    console.error('ZIP city lookup failed:', e?.message || e);
    if (!city || city === 'Unknown') {
      city = `ZIP ${zipCode}`;
    }
  }
  return { city, adr, occupancy };
}

// Helper: lookup city/state from ZIP via Zippopotam.us (no API key required)
async function lookupCityFromZip(zipCode) {
  try {
    const res = await fetch(`https://api.zippopotam.us/us/${encodeURIComponent(zipCode)}`);
    if (!res.ok) return null;
    const j = await res.json();
    const place = j?.places?.[0];
    if (!place) return null;
    const city = place['place name'];
    const state = place['state abbreviation'] || place['state'];
    if (city && state) return `${city}, ${state}`;
    return city || null;
  } catch (e) {
    return null;
  }
}

// Helper: build polished XLSX with multiple sheets and formulas
async function buildWorkbook({ firstName, lastName, email, zipCode, city, adr, occupancy }) {
  const ExcelJS = require('exceljs');
  const workbook = new ExcelJS.Workbook();
  // Ensure formulas recalc on open in Excel
  workbook.calcProperties.fullCalcOnLoad = true;
  workbook.calcProperties.calcId = 124519;

  const createdAt = new Date();
  const createdAtStr = createdAt.toLocaleString('en-US', { year: 'numeric', month: 'short', day: '2-digit' });

  // Common styling helpers
  const headerFill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFEFEFEF' } };
  const headerBorder = { top: { style: 'thin' }, left: { style: 'thin' }, bottom: { style: 'thin' }, right: { style: 'thin' } };
  const inputFill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFF5F5F5' } };

  // helper to apply thin borders to a rectangular region
  function addThinBorders(ws, startRow, endRow, startCol, endCol) {
    for (let r = startRow; r <= endRow; r++) {
      const row = ws.getRow(r);
      for (let c = startCol; c <= endCol; c++) {
        const cell = row.getCell(c);
        cell.border = { top: { style: 'thin' }, left: { style: 'thin' }, bottom: { style: 'thin' }, right: { style: 'thin' } };
      }
    }
  }

  // helper to bump default font size across used cells
  function setDefaultFont(ws, size) {
    ws.eachRow({ includeEmpty: false }, (row) => {
      row.eachCell({ includeEmpty: false }, (cell) => {
        const f = cell.font || {};
        // Preserve any explicitly-set size; only apply default if absent
        cell.font = { ...f, size: f.size || size };
      });
    });
  }

  // Sheet: Summary (first)
  const summary = workbook.addWorksheet('Summary');
  summary.properties.defaultRowHeight = 18;
  summary.getColumn(1).width = 26; summary.getColumn(2).width = 18; summary.getColumn(3).width = 18; summary.getColumn(4).width = 18;
  summary.addRow(['Property Earnings Estimate']).font = { bold: true, size: 22 };
  summary.mergeCells('A1:D1');
  summary.getRow(1).alignment = { horizontal: 'center' };
  summary.getRow(1).height = 28;
  summary.addRow(['This tool provides estimated host earnings for potential listing on Airbnb. Actual results may vary depending on demand, seasonality, and listing quality.']);
  summary.mergeCells('A2:D2');
  summary.getCell('A2').alignment = { wrapText: true };
  summary.getRow(2).height = 42;
  summary.addRow(['Generated', createdAtStr]);
  summary.addRow(['Name', `${(firstName||'')} ${(lastName||'')}`.trim() ]);
  summary.addRow(['ZIP / City', `${zipCode} / ${city}`]);
  summary.addRow([]);
  summary.addRow(['Assumptions']).font = { bold: true };
  summary.addRow(['Nightly Rate (Blended ADR)', { formula: "Host_Calculator!B8" }]);
  summary.addRow(['Occupancy (Blended)', { formula: "Host_Calculator!B9" }]);
  summary.addRow(['Airbnb Service Fee', { formula: "Host_Calculator!B5" }]);
  summary.getCell('B8').numFmt = '$#,##0';
  summary.getCell('B9').numFmt = '0%';
  summary.getCell('B10').numFmt = '0%';
  summary.addRow([]);
  summary.addRow(['Scenario', 'Monthly Gross', 'Annual Gross', 'Net Annual (after fee)']).font = { bold: true };
  const sumStart = summary.rowCount + 1;
  const scenarioResultRows = [];
  [['Low'],['Medium'],['High']].forEach(([name]) => {
    const r = summary.addRow([name, null, null, null]);
    summary.getCell(`B${r.number}`).numFmt = '$#,##0';
    summary.getCell(`C${r.number}`).numFmt = '$#,##0';
    summary.getCell(`D${r.number}`).numFmt = '$#,##0';
    scenarioResultRows.push(r.number);
  });
  const sumHeader = summary.getRow(sumStart - 1);
  sumHeader.eachCell((c)=>{ c.fill = headerFill; c.border = headerBorder; });
  // borders around the summary scenario table
  addThinBorders(summary, sumStart - 1, sumStart + 2, 1, 4);

  // Sheet: Market Data (second) - Use underscore for compatibility
  const market = workbook.addWorksheet('Market_Data');
  market.properties.defaultRowHeight = 18;
  market.columns = [
    { key: 'season', width: 16 },
    { key: 'adr', width: 14 },
    { key: 'occ', width: 14 },
    { key: 'weight', width: 16 }
  ];
  // Title and spacing
  const mdTitle = market.addRow(['Market Data']);
  mdTitle.font = { bold: true, size: 22 };
  market.mergeCells('A1:D1');
  market.getRow(1).alignment = { horizontal: 'center' };
  market.getRow(1).height = 28;
  market.addRow([]);
  // Table header
  const mdHeader = market.addRow(['Season', 'ADR (USD)', 'Occupancy %', 'Weight of Year %']);
  mdHeader.font = { bold: true };
  mdHeader.alignment = { vertical: 'middle', horizontal: 'center' };
  mdHeader.eachCell((c) => { c.fill = headerFill; c.border = headerBorder; });
  const seasons = ['High', 'Shoulder', 'Low', 'Holiday', 'Event'];
  const adrDefaults = { High: adr.High || 0, Shoulder: adr.Shoulder || 0, Low: adr.Low || 0, Holiday: adr.Holiday || 0, Event: adr.Event || 0 };
  const occDefault = occupancy || 65;
  const defaultWeights = { High: 30, Shoulder: 25, Low: 25, Holiday: 10, Event: 10 };
  seasons.forEach((s) => {
    const row = market.addRow({
      season: s,
      adr: adrDefaults[s] || 0,
      occ: (occDefault / 100),
      weight: defaultWeights[s] ? (defaultWeights[s] / 100) : null
    });
    // Shade input cells for user edits
    ['B', 'C', 'D'].forEach((col) => {
      const cell = market.getCell(`${col}${row.number}`);
      cell.fill = inputFill;
    });
  });
  // Number formats
  for (let r = 4; r <= 8; r++) {
    market.getCell(`B${r}`).numFmt = '$#,##0';
    market.getCell(`C${r}`).numFmt = '0%';
    market.getCell(`D${r}`).numFmt = '0%';
  }
  market.views = [{ state: 'frozen', xSplit: 0, ySplit: 3 }];

  // Sheet: Host Calculator - Use underscore for compatibility
  const host = workbook.addWorksheet('Host_Calculator');
  host.properties.defaultRowHeight = 18;
  host.getColumn(1).width = 36;
  host.getColumn(2).width = 18;
  host.getColumn(3).width = 18;
  host.getColumn(4).width = 18;
  // Title and spacing
  const hcTitle = host.addRow(['Host Calculator']);
  hcTitle.font = { bold: true, size: 22 };
  host.mergeCells('A1:D1');
  host.getRow(1).alignment = { horizontal: 'center' };
  host.getRow(1).height = 28;
  host.addRow([]);

  host.addRow(['Assumptions']).font = { bold: true };
  host.addRow(['Nights per Month', 30]); // B4
  host.addRow(['Airbnb Service Fee', 0.03]); // B5
  host.addRow(['Scenario Multipliers (Low / Med / High)', 0.50, 0.65, 0.80]); // B6..D6
  // Shade input cells
  ['B4','B5','B6','C6','D6'].forEach(addr => host.getCell(addr).fill = inputFill);
  host.getCell('B5').numFmt = '0%';
  host.getCell('B6').numFmt = '0%'; host.getCell('C6').numFmt = '0%'; host.getCell('D6').numFmt = '0%';
  // Ensure multiple calculation chains recalc properly
  workbook.calcProperties.calcId = 124519;

  host.addRow([]);
  // COMPATIBILITY FIX: Use simpler formulas that work in both Excel and Google Sheets
  // Instead of IFERROR with complex SUMPRODUCT division, use IF with an explicit check.
  host.addRow(['Blended ADR (weighted by Market Data)', { formula: "IF(SUM(Market_Data!D4:D8)=0,0,SUMPRODUCT(Market_Data!B4:B8,Market_Data!D4:D8)/SUM(Market_Data!D4:D8))" }]);
  host.addRow(['Blended Occupancy (weighted by Market Data)', { formula: "IF(SUM(Market_Data!D4:D8)=0,0,SUMPRODUCT(Market_Data!C4:C8,Market_Data!D4:D8)/SUM(Market_Data!D4:D8))" }]);
  host.getCell('B8').numFmt = '$#,##0';
  host.getCell('B9').numFmt = '0%';

  host.addRow([]);
  host.addRow(['Scenario', 'Monthly Gross', 'Annual Gross', 'Net Annual (after fee)']).font = { bold: true };
  const startRow = host.rowCount + 1;
  const scenarios = [
    { name: 'Low', multRef: 'B6' },
    { name: 'Medium', multRef: 'C6' },
    { name: 'High', multRef: 'D6' }
  ];
  const scenarioRows = [];
  scenarios.forEach((sc) => {
    const r = host.addRow([sc.name, null, null, null]);
    // COMPATIBILITY FIX: Use simpler formulas with absolute references
    host.getCell(`B${r.number}`).value = { formula: `$B$8*($B$9*${sc.multRef})*$B$4` };
    host.getCell(`C${r.number}`).value = { formula: `B${r.number}*12` };
    host.getCell(`D${r.number}`).value = { formula: `C${r.number}*(1-$B$5)` };
    host.getCell(`B${r.number}`).numFmt = '$#,##0';
    host.getCell(`C${r.number}`).numFmt = '$#,##0';
    host.getCell(`D${r.number}`).numFmt = '$#,##0';
    scenarioRows.push(r.number);
  });
  const headerRowHost = host.getRow(startRow - 1);
  headerRowHost.eachCell((c)=>{ c.fill = headerFill; c.border = headerBorder; });
  // borders around the scenario table on Host sheet
  addThinBorders(host, startRow - 1, Math.max(...scenarioRows), 1, 4);
  // borders around Assumptions tables
  addThinBorders(host, 3, 6, 1, 4); // A3:D6
  addThinBorders(host, 8, 9, 1, 2); // A8:B9

  // Optional Chart Data for easy Excel chart insertion
  host.addRow([]);
  const chartTitleRow = host.addRow(['Chart Data (Annual Gross)']);
  chartTitleRow.font = { bold: true };
  const chartHeaderRow = host.addRow(['Scenario', 'Annual Gross']);
  chartHeaderRow.font = { bold: true };
  scenarios.forEach((sc, i) => {
    const r = host.addRow([
      sc.name,
      { formula: `C${scenarioRows[i]}` }
    ]);
    r.getCell(2).numFmt = '$#,##0';
  });
  addThinBorders(host, chartHeaderRow.number, host.rowCount, 1, 2);

  // Link summary sheet back to calculator
  scenarioRows.forEach((calcRow, i) => {
    const sumRow = scenarioResultRows[i];
    summary.getCell(`B${sumRow}`).value = { formula: `Host_Calculator!B${calcRow}` };
    summary.getCell(`C${sumRow}`).value = { formula: `Host_Calculator!C${calcRow}` };
    summary.getCell(`D${sumRow}`).value = { formula: `Host_Calculator!D${calcRow}` };
  });

  // Apply larger default font size across sheets (without overwriting bold/italic)
  [summary, market, host].forEach(ws => setDefaultFont(ws, 12));

  return workbook;
}

// Calculator endpoint handler
async function handleCalculator(req, res) {
  try {
    const body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
    const { zipCode, firstName = '', lastName = '', email = '' } = body || {};

    if (!zipCode || !/^\d{5}$/.test(String(zipCode))) {
      return res.status(400).json({ error: 'Invalid zipCode. Provide 5-digit ZIP.' });
    }

    // Save submission (zip-only allowed) with message "Calculator"
    const now = new Date().toISOString();
    let id = email && isValidEmail(email) ? email : `submission-${Date.now()}-${randomUUID()}`;
    const putParams = {
      TableName: tableName,
      Item: {
        id,
        firstName,
        lastName,
        email: email || 'N/A',
        zipCode,
        message: 'Calculator',
        createdAt: now
      }
    };
    let saved = true;
    try {
      await ddbDocClient.send(new PutCommand(putParams));
      console.log('Calculator saved to DDB:', id);
    } catch (e) {
      console.error('DDB save failed (continuing):', e);
      saved = false;
    }

    // Email notification when contact provided
    if (email && isValidEmail(email)) {
      try {
        await sendEmailNotification(firstName || 'N/A', lastName || 'N/A', email, 'Calculator');
      } catch (e) {
        console.error('Email send failed (continuing):', e);
      }
    }

    // Fetch insights from Gemini
    const insights = await fetchZipInsights(zipCode);

    // Build workbook and return as base64 JSON to avoid API Gateway binary issues
    const workbook = await buildWorkbook({ firstName, lastName, email, zipCode, ...insights });
    const buffer = await workbook.xlsx.writeBuffer();
    const fileName = `Guestrix_Earnings_Estimate_${zipCode}.xlsx`;
    const mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    res.status(200).json({
      id,
      fileName,
      mimeType,
      dataBase64: Buffer.from(buffer).toString('base64'),
      saved
    });
  } catch (err) {
    console.error('Calculator error:', err);
    res.status(500).json({ error: 'Failed to generate estimate' });
  }
}

// Bind routes for both top-level and nested paths
app.post(calcPath, handleCalculator);
app.post(path + calcPath, handleCalculator);

// Fee Comparison endpoint handler
function buildFeeComparisonPdf({ firstName, lastName, nightly, nights, cleaning, tax, otherFees = 0, discount = 0, marketing = 8 }) {
  return new Promise((resolve, reject) => {
    try {
      const doc = new PDFDocument({ size: 'LETTER', margin: 50 });
      const chunks = [];
      doc.on('data', (c) => chunks.push(c));
      doc.on('end', () => resolve(Buffer.concat(chunks)));

      const nameLine = `${(firstName || '').trim()} ${(lastName || '').trim()}`.trim() || 'Guest';
      const createdAt = new Date();
      const createdAtStr = createdAt.toLocaleString('en-US');

      // Title
      doc.fontSize(20).fillColor('#161032').text('Guestrix - Vacation Rental Fee Comparison', { align: 'center' });
      doc.moveDown(0.5);
      doc.fontSize(12).fillColor('#333333').text(`Generated: ${createdAtStr}`, { align: 'center' });
      doc.moveDown(1);
      doc.fontSize(14).fillColor('#161032').text(`Name: ${nameLine}`);
      doc.moveDown(0.5);

      // Inputs (only the ones used in calculation)
      doc.fontSize(12).fillColor('#333333').text('Inputs:', { underline: true });
      doc.moveDown(0.25);
      doc.text(`Nightly Rate ($): ${Number(nightly || 0).toFixed(2)}`);
      doc.text(`Number of Nights: ${Number(nights || 0)}`);
      doc.text(`Cleaning Fee ($): ${Number(cleaning || 0).toFixed(2)}`);
      doc.moveDown(0.75);

      // Calculations (host payout oriented)
      const night = Number(nightly || 0);
      const numNights = Number(nights || 0);
      const cleaningFee = Number(cleaning || 0);
      const other = Number(otherFees || 0);
      // Simplified calculation (matching frontend)
      const base = night * numNights + cleaningFee;
      const abnbBefore_guestFee = base * 0.14;
      const abnbBefore_hostPayout = base * (1 - 0.03);
      const abnbAfter_hostPayout = base * (1 - 0.155);
      const targetPayout = abnbBefore_hostPayout;
      const baseAdj = targetPayout / (1 - 0.155);
      const nightlyAdj = numNights > 0 ? (baseAdj - cleaningFee) / numNights : 0;
      const abnbAdj_hostPayout = targetPayout;
      const vrbo_hostPayout = base * (1 - 0.08);
      const booking_hostPayout = base * (1 - 0.15);

      // Table Header (Nightly, Guest Fee, Total Guest, Host Payout)
      doc.fontSize(12).fillColor('#161032').text('Comparison Table:', { underline: true });
      doc.moveDown(0.25);
      const startX = doc.x;
      const startY = doc.y;
      // Proportional column widths based on numeric content (LETTER size = 612pt, margins = 100pt, available = 512pt)
      const colWidths = [150, 90, 100, 100, 72];
      const headers = ['Platform & Scenario', 'Nightly Rate', 'Guest Service Fee', 'Total Guest Price', 'Host Payout'];
      const rows = [
        ['Airbnb (PMS) BEFORE Oct 27', night, abnbBefore_guestFee, base + abnbBefore_guestFee, abnbBefore_hostPayout],
        ['Airbnb (PMS) AFTER Oct 27', night, 0, base, abnbAfter_hostPayout],
        ['Airbnb Adjusted Price (PMS)*', nightlyAdj, 0, baseAdj, abnbAdj_hostPayout],
        ['VRBO', night, base * 0.08, base + (base * 0.08), vrbo_hostPayout],
        ['Booking.com', night, 0, base, booking_hostPayout]
      ];

      function drawCell(text, x, y, w, alignRight, isHeader = false) {
        const cellHeight = isHeader ? 30 : 20; // Taller cells for headers to allow wrapping
        doc.rect(x, y, w, cellHeight).strokeColor('#e5e7eb').lineWidth(0.5).stroke();
        doc.fillColor('#333333').fontSize(10);
        const opts = { width: w - 6, align: alignRight ? 'right' : 'left' };
        doc.text(text, x + 3, y + 4, opts);
      }
      // Header row
      let cx = startX, cy = startY;
      headers.forEach((h, i) => {
        drawCell(h, cx, cy, colWidths[i], false, true); // isHeader = true for taller cells
        cx += colWidths[i];
      });
      cy += 30; // Account for taller header cells
      // Data rows
      rows.forEach((r) => {
        cx = startX;
        drawCell(r[0], cx, cy, colWidths[0], false); cx += colWidths[0];
        drawCell(`$${Number(r[1]).toFixed(2)}`, cx, cy, colWidths[1], true); cx += colWidths[1];
        drawCell(`${Number(r[2]) ? '$' + Number(r[2]).toFixed(2) : '$0.00' }`, cx, cy, colWidths[2], true); cx += colWidths[2];
        drawCell(`$${Number(r[3]).toFixed(2)}`, cx, cy, colWidths[3], true); cx += colWidths[3];
        drawCell(`$${Number(r[4]).toFixed(2)}`, cx, cy, colWidths[4], true);
        cy += 20;
      });

      doc.moveDown(1.5);
      // Simple Bar Chart — ensure it fits on one page and is centered
      const max = Math.max(abnbBefore_hostPayout, abnbAfter_hostPayout, abnbAdj_hostPayout, vrbo_hostPayout, booking_hostPayout) || 1;
      const maxBarHeight = 200;
      const barWidth = 40;
      const gap = 30;
      const series = [
        { label: 'Airbnb BEFORE', total: abnbBefore_hostPayout, color: '#ee6055' },
        { label: 'Airbnb AFTER', total: abnbAfter_hostPayout, color: '#f39c12' },
        { label: 'Airbnb Adjusted*', total: abnbAdj_hostPayout, color: '#7cb342' },
        { label: 'Vrbo', total: vrbo_hostPayout, color: '#2a9d8f' },
        { label: 'Booking', total: booking_hostPayout, color: '#161032' }
      ];
      const totalChartWidth = series.length * barWidth + (series.length - 1) * gap;
      const pageWidth = doc.page.width;
      const pageHeight = doc.page.height;
      const margins = doc.page.margins || { left: 50, right: 50, top: 50, bottom: 50 };
      const availableWidth = pageWidth - margins.left - margins.right;
      const chartNeededHeight = 20 /*title*/ + 8 + maxBarHeight + 20 /*labels*/ + 10;
      const availableHeight = pageHeight - margins.bottom - doc.y;
      if (chartNeededHeight > availableHeight) {
        doc.addPage();
        doc.y = doc.page.margins.top; // Reset Y to top of new page
      }
      
      // Center the chart header properly - ensure it's visible
      doc.fontSize(14).fillColor('#161032').text('Host Payout Comparison', { align: 'center', width: doc.page.width - doc.page.margins.left - doc.page.margins.right, lineBreak: false });
      doc.moveDown(0.5);
      const startYForChart = doc.y + 10;
      const chartX = margins.left + Math.max(0, Math.floor((availableWidth - totalChartWidth) / 2));
      const chartY = startYForChart;
      const baselineY = chartY + maxBarHeight;
      const mult = (max > 0 ? maxBarHeight / max : 1);
      let bx = chartX;
      series.forEach((s) => {
        const h = Math.round(s.total * mult);
        if (s.color) doc.fillColor(s.color);
        doc.rect(bx, baselineY - h, barWidth, h).fill();
        if (s.border) {
          doc.strokeColor(s.border).lineWidth(0.5).rect(bx, baselineY - h, barWidth, h).stroke();
        }
        // Labels (avoid pagination by ensuring within current page area)
        doc.fillColor('#333333').fontSize(10).text(s.label, bx - 5, baselineY + 5, { width: barWidth + 10, align: 'center', lineBreak: false });
        bx += barWidth + gap;
      });

      // Add footnote after chart with more spacing
      doc.moveDown(2);
      // Reset to left margin and add footnote
      doc.x = doc.page.margins.left;
      doc.fontSize(10).fillColor('#666666').font('Helvetica-Oblique').text('* Airbnb Adjusted Price to achieve the same payout as before Oct 27 (with PMS)', { align: 'left', width: doc.page.width - doc.page.margins.left - doc.page.margins.right });
      doc.font('Helvetica'); // Reset font

      doc.end();
    } catch (e) {
      reject(e);
    }
  });
}

async function handleFeeComparison(req, res) {
  try {
    const body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
    const { firstName = '', lastName = '', email = '', nightly = null, nights = null, cleaning = null, tax = null, otherFees = 0, discount = 0, marketing = 8, message = 'Fee Comparison Tool' } = body || {};

    // Build item for DynamoDB: save ZIP-only too, with generated id when email absent
    let id = email && isValidEmail(email) ? email : `submission-${Date.now()}-${randomUUID()}`;
    const item = {
      id,
      firstName,
      lastName,
      email: email || 'N/A',
      nightly,
      nights,
      cleaning,
      tax,
      otherFees,
      discount,
      marketing,
      message: message || 'Fee Comparison Tool',
      createdAt: new Date().toISOString()
    };

    let saved = true;
    try {
      await ddbDocClient.send(new PutCommand({ TableName: tableName, Item: item }));
      console.log('Fee Comparison saved to DDB:', id);
    } catch (e) {
      console.error('DDB save failed (continuing):', e);
      saved = false;
    }

    // Email notifications: only when email provided and valid; omit when ZIP-only
    if (email && isValidEmail(email)) {
      try {
        await sendEmailNotification(firstName || 'N/A', lastName || 'N/A', email, message || 'Fee Comparison Tool');
      } catch (e) {
        console.error('Email send failed (continuing):', e);
      }
    }

    // Lightweight tracking mode (e.g., WhatsApp link clicks): skip PDF generation
    if (message === 'Whatsapp link clicked' || body.track === true) {
      return res.status(200).json({ id, success: true });
    }

    // Generate PDF and return as base64 JSON
    let pdfBuffer;
    try {
      pdfBuffer = await buildFeeComparisonPdf({ firstName, lastName, nightly, nights, cleaning, tax, otherFees, discount, marketing });
    } catch (e) {
      console.error('PDF generation failed:', e?.message || e);
      // Fall back to simple success JSON if PDF fails
      return res.status(200).json({ success: true, id, saved });
    }
    const safeName = `${(firstName||'')}_${(lastName||'')}`.replace(/[^a-z0-9_\-]+/ig, '').replace(/^_+|_+$/g, '') || 'Guest';
    const fileName = `Guestrix_Fee_Comparison_${safeName}.pdf`;
    const mimeType = 'application/pdf';
    return res.status(200).json({ id, fileName, mimeType, dataBase64: Buffer.from(pdfBuffer).toString('base64'), saved });
  } catch (err) {
    console.error('Fee Comparison error:', err);
    res.status(500).json({ error: 'Failed to process fee comparison submission' });
  }
}

// Bind routes for both top-level and nested paths
app.post(feeComparisonPath, handleFeeComparison);
app.post(path + feeComparisonPath, handleFeeComparison);

// Listing Optimizer (Gemini) — do not persist Gemini outputs
async function optimizeListingWithGemini({ title, description }) {
  let apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    try {
      const envText = fs.readFileSync(__dirname + '/.env', 'utf8');
      const match = envText.split(/\r?\n/).find((l) => l.trim().startsWith('GEMINI_API_KEY='));
      if (match) apiKey = match.split('=')[1].trim();
    } catch (_) {}
  }
  if (!apiKey) {
    // graceful fallback
    return {
      optimizedTitle: title,
      optimizedDescription: description,
      scores: { guestAppeal: 70, bookingPotential: 70, searchVisibility: 70, trustClarity: 70 },
      suggestions: {
        guestAppeal: ["Highlight unique amenities", "Add neighborhood vibe", "Tighten headline"],
        bookingPotential: ["Clarify rules early", "Mention discounts", "Add urgency words"],
        searchVisibility: ["Include city/area", "Use lodging keywords", "Add bed/bath counts"],
        trustClarity: ["Set expectations", "Clarify check-in", "Note cleanliness steps"]
      }
    };
  }
  const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key=' + encodeURIComponent(apiKey);
  const prompt = `You improve vacation rental listings for all major platforms (Airbnb, Vrbo, Booking.com). Given a current title and description, create an optimized version that maximizes guest appeal, booking potential, search visibility, and trust & clarity. Respect typical title limits across platforms (~50-60 characters preferred). Return ONLY strict JSON in this exact shape with numeric 0-100 scores and exactly 3 suggestions per category:
{
  "optimizedTitle": "...",
  "optimizedDescription": "...",
  "scores": {
    "guestAppeal": 0,
    "bookingPotential": 0,
    "searchVisibility": 0,
    "trustClarity": 0
  },
  "suggestions": {
    "guestAppeal": ["s1","s2","s3"],
    "bookingPotential": ["s1","s2","s3"],
    "searchVisibility": ["s1","s2","s3"],
    "trustClarity": ["s1","s2","s3"]
  }
}
Use concise, on-brand copy. Title must be under 60 chars when possible.`;
  const body = {
    contents: [{ role: 'user', parts: [{ text: `Title: ${title}\nDescription: ${description}\n\n${prompt}` }]}]
  };
  const resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!resp.ok) {
    return { optimizedTitle: title, optimizedDescription: description, scores: { guestAppeal: 70, bookingPotential: 70, searchVisibility: 70, trustClarity: 70 }, suggestions: { guestAppeal: [], bookingPotential: [], searchVisibility: [], trustClarity: [] } };
  }
  const data = await resp.json().catch(() => ({}));
  let text = data?.candidates?.[0]?.content?.parts?.[0]?.text || '';
  if (text.startsWith('```')) text = text.replace(/^```[a-z]*\s*/i, '').replace(/\s*```$/,'');
  let parsed;
  try { parsed = JSON.parse(text); } catch (_) {
    return { optimizedTitle: title, optimizedDescription: description, scores: { guestAppeal: 70, bookingPotential: 70, searchVisibility: 70, trustClarity: 70 }, suggestions: { guestAppeal: [], bookingPotential: [], searchVisibility: [], trustClarity: [] } };
  }
  function clamp(n){ n = Number(n); if (!isFinite(n)) return 70; return Math.max(0, Math.min(100, Math.round(n))); }
  parsed.scores = parsed.scores || {};
  parsed.scores.guestAppeal = clamp(parsed.scores.guestAppeal);
  parsed.scores.bookingPotential = clamp(parsed.scores.bookingPotential);
  parsed.scores.searchVisibility = clamp(parsed.scores.searchVisibility);
  parsed.scores.trustClarity = clamp(parsed.scores.trustClarity);
  return parsed;
}

async function handleListingOptimizer(req, res) {
  try {
    const body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
    const { title, description, firstName = '', lastName = '', email = '' } = body || {};
    if (!title || !description) {
      return res.status(400).json({ error: 'title and description are required' });
    }
    // Save inputs to WaitList
    const id = email && isValidEmail(email) ? email : `submission-${Date.now()}-${randomUUID()}`;
    const putParams = {
      TableName: tableName,
      Item: { id, firstName, lastName, email: email || 'N/A', title, description, message: 'Listing Optimizer', createdAt: new Date().toISOString() }
    };
    let saved = true;
    try { 
      await ddbDocClient.send(new PutCommand(putParams)); 
      console.log('Listing Optimizer saved to DDB:', id);
    } catch (e) { 
      console.error('DDB save failed (continuing):', e); 
      saved = false;
    }
    if (email && isValidEmail(email)) {
      try { await sendEmailNotification(firstName || 'N/A', lastName || 'N/A', email, 'Listing Optimizer'); } catch (e) { console.error('Email send failed (continuing):', e); }
    }
    // Optimize via Gemini
    const result = await optimizeListingWithGemini({ title, description });
    return res.status(200).json({ id, result, saved });
  } catch (err) {
    console.error('Listing Optimizer error:', err);
    res.status(500).json({ error: 'Failed to optimize listing' });
  }
}

app.post(listingOptimizerPath, handleListingOptimizer);
app.post(path + listingOptimizerPath, handleListingOptimizer);

// Rating endpoint — attach rating 1–5 to an existing submission id
async function handleRating(req, res) {
  try {
    const body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
    const { id, rating } = body || {};
    const r = Number(rating);
    if (!id || !(r >= 1 && r <= 5)) {
      return res.status(400).json({ error: 'id and rating (1-5) required' });
    }
    const params = {
      TableName: tableName,
      Key: { id },
      UpdateExpression: 'SET #rating = :r, ratedAt = :t',
      ExpressionAttributeNames: { '#rating': 'rating' },
      ExpressionAttributeValues: { ':r': r, ':t': new Date().toISOString() },
      ReturnValues: 'UPDATED_NEW',
      // Ensure we only update existing submissions; avoid accidental upsert
      ConditionExpression: 'attribute_exists(id)'
    };
    await ddbDocClient.send(new UpdateCommand(params));
    console.log('Rating saved successfully', { id, rating: r, tableName });
    return res.status(200).json({ success: true });
  } catch (err) {
    if (err && (err.name === 'ConditionalCheckFailedException' || err.code === 'ConditionalCheckFailedException')) {
      console.warn('Rating failed: submission not found', { id });
      return res.status(404).json({ error: 'Submission not found' });
    }
    console.error('Rating error:', {
      error: err,
      tableName,
      region: process.env.TABLE_REGION || process.env.REGION || 'us-east-2',
      context: 'update rating'
    });
    return res.status(500).json({ error: 'Failed to save rating' });
  }
}

app.post(ratingPath, handleRating);
app.post(path + ratingPath, handleRating);


/************************************
* HTTP post method for insert object *
*************************************/

app.post(path, async function(req, res) {
  console.log('Request body:', req.body);
  
  // Parse the body if it's a string (API Gateway sends stringified JSON)
  const body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
  const { firstName, lastName, email, message } = body;
  const id = email; // using email as the id for waitlist entries

  // Input validation
  if (!firstName || !lastName || !email) {
    console.log('Validation failed: Missing required fields');
    return res.status(400).json({
      error: 'Missing required fields',
      message: 'First name, last name, and email are required'
    });
  }

  if (!isValidEmail(email)) {
    console.log('Validation failed: Invalid email format');
    return res.status(400).json({
      error: 'Invalid email format',
      message: 'Please provide a valid email address'
    });
  }

  const params = {
    TableName: tableName,
    Item: {
      id: email, // Using email as the partition key
      firstName,
      lastName,
      email,
      message: message || '', // Include message field, default to empty string if not provided
      createdAt: new Date().toISOString()
    }
  };

  try {
    console.log('Adding to waitlist:', params.Item);

    // Store in DynamoDB
    await ddbDocClient.send(new PutCommand(params));
    console.log('Successfully added to waitlist');

    // Send email notification
    const emailResult = await sendEmailNotification(firstName, lastName, email, message);
    if (emailResult.success) {
      console.log('Email notification sent successfully');
    } else {
      console.error('Failed to send email notification:', emailResult.error);
      // Don't fail the request if email fails, just log it
    }

    return res.status(200).json({
      success: true,
      id,
      message: 'Successfully added to waitlist'
    });
  } catch (error) {
    console.error('Error adding to waitlist:', {
      error,
      tableName,
      id,
      region: process.env.TABLE_REGION || process.env.REGION || 'us-east-2'
    });
    return res.status(500).json({
      error: 'Failed to add to waitlist',
      message: 'An error occurred while processing your request'
    });
  }
});

/**************************************
* HTTP remove method to delete object *
***************************************/

app.delete(path + '/object' + hashKeyPath + sortKeyPath, async function(req, res) {
  const params = {};
  if (userIdPresent && req.apiGateway) {
    params[partitionKeyName] = req.apiGateway.event.requestContext.identity.cognitoIdentityId || UNAUTH;
  } else {
    params[partitionKeyName] = req.params[partitionKeyName];
     try {
      params[partitionKeyName] = convertUrlType(req.params[partitionKeyName], partitionKeyType);
    } catch(err) {
      res.statusCode = 500;
      res.json({error: 'Wrong column type ' + err});
    }
  }
  if (hasSortKey) {
    try {
      params[sortKeyName] = convertUrlType(req.params[sortKeyName], sortKeyType);
    } catch(err) {
      res.statusCode = 500;
      res.json({error: 'Wrong column type ' + err});
    }
  }

  let removeItemParams = {
    TableName: tableName,
    Key: params
  }

  try {
    let data = await ddbDocClient.send(new DeleteCommand(removeItemParams));
    res.json({url: req.url, data: data});
  } catch (err) {
    res.statusCode = 500;
    res.json({error: err, url: req.url});
  }
});

app.listen(3000, function() {
  console.log("App started")
});

// Export the app object. When executing the application local this does nothing. However,
// to port it to AWS Lambda we will create a wrapper around that will load the app from
// this file
module.exports = app
