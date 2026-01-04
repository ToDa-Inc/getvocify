/**
 * Setup Script
 * Handles one-time microphone permission grant
 */

const allowButton = document.getElementById('allow-button');
const successMsg = document.getElementById('success-msg');

allowButton.addEventListener('click', async () => {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach(track => track.stop());
    
    allowButton.style.display = 'none';
    successMsg.style.display = 'block';
    
    // Automatically close after 2 seconds
    setTimeout(() => {
      window.close();
    }, 2000);
  } catch (error) {
    console.error('Permission denied:', error);
    alert('Microphone permission was denied. Please click the camera icon in your address bar to allow access.');
  }
});
