// Daily Quest JavaScript
// Handles animations and interactions for Daily Quest page

document.addEventListener('DOMContentLoaded', function() {
    console.log('Daily Quest page loaded');
    
    // Animate progress bar on load
    animateProgressBar();
    
    // Add hover effects to task cards
    addTaskCardEffects();
});

function animateProgressBar() {
    const progressFill = document.querySelector('.progress-fill');
    if (progressFill) {
        const targetWidth = progressFill.style.width;
        progressFill.style.width = '0%';
        
        setTimeout(() => {
            progressFill.style.width = targetWidth;
        }, 300);
    }
}

function addTaskCardEffects() {
    const taskCards = document.querySelectorAll('.task-card');
    
    taskCards.forEach((card, index) => {
        // Stagger animation on load
        card.style.opacity = '0';
        card.style.transform = 'translateY(20px)';
        
        setTimeout(() => {
            card.style.transition = 'all 0.5s ease';
            card.style.opacity = '1';
            card.style.transform = 'translateY(0)';
        }, 100 * index);
    });
}

// Update streak display with animation
function updateStreakDisplay(newStreak) {
    const streakNumber = document.querySelector('.streak-number');
    if (streakNumber) {
        const currentStreak = parseInt(streakNumber.textContent);
        
        if (newStreak > currentStreak) {
            // Animate increment
            streakNumber.style.transform = 'scale(1.5)';
            streakNumber.textContent = newStreak;
            
            setTimeout(() => {
                streakNumber.style.transform = 'scale(1)';
            }, 500);
        }
    }
}

// Fetch and update daily quest status
function updateDailyQuestStatus() {
    fetch('/api/daily/status')
        .then(response => response.json())
        .then(data => {
            if (data.exists) {
                // Update progress
                const progressFill = document.querySelector('.progress-fill');
                const progressText = document.querySelector('.progress-text');
                
                if (progressFill && progressText) {
                    const percentage = (data.completed / data.total) * 100;
                    progressFill.style.width = percentage + '%';
                    progressText.textContent = `${data.completed} / ${data.total} задач`;
                }
                
                // Update streak
                updateStreakDisplay(data.streak);
            }
        })
        .catch(error => {
            console.error('Error fetching daily quest status:', error);
        });
}

// Auto-refresh status every 30 seconds
setInterval(updateDailyQuestStatus, 30000);
