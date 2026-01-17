/**
 * Gemini Audio Processor
 * 
 * This AudioWorklet processor captures audio data from the microphone
 * and processes it for sending to the Gemini Live API.
 */

class AudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 4096; // Buffer size
    this.buffer = new Float32Array(this.bufferSize);
    this.bufferIndex = 0;
  }

  process(inputs, outputs, parameters) {
    // Get input audio
    const input = inputs[0];
    
    // Check if we have audio data
    if (input.length > 0) {
      const inputChannel = input[0];
      
      // Copy samples to our buffer
      for (let i = 0; i < inputChannel.length; i++) {
        this.buffer[this.bufferIndex] = inputChannel[i];
        this.bufferIndex++;
        
        // When buffer is full, send it to the main thread
        if (this.bufferIndex >= this.bufferSize) {
          this.sendBufferToMainThread();
        }
      }
    }
    
    // Keep processor running
    return true;
  }
  
  sendBufferToMainThread() {
    // Convert Float32Array to Int16Array (what Gemini expects)
    const pcmData = new Int16Array(this.bufferSize);
    for (let i = 0; i < this.bufferSize; i++) {
      // Convert from float (-1.0 to 1.0) to int16 (-32768 to 32767)
      pcmData[i] = Math.max(-32768, Math.min(32767, Math.floor(this.buffer[i] * 32767)));
    }
    
    // Send the buffer to the main thread
    this.port.postMessage({
      audioData: pcmData.buffer
    }, [pcmData.buffer]); // Transfer buffer ownership for efficiency
    
    // Reset buffer index
    this.bufferIndex = 0;
    this.buffer = new Float32Array(this.bufferSize);
  }
}

// Register the processor
registerProcessor('audio-processor', AudioProcessor); 