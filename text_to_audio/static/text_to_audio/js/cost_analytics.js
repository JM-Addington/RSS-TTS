// AIDEV-NOTE: Extracted from cost_analytics.html. Chart data passed via #chart-data JSON block.
(function() {
'use strict';

document.addEventListener('DOMContentLoaded', function() {
  const chartDataEl = document.getElementById('chart-data');
  if (!chartDataEl) return;

  const chartData = JSON.parse(chartDataEl.textContent);

  // Cost Over Time Chart
  const timeCtx = document.getElementById('costOverTimeChart');
  if (timeCtx && chartData.costsOverTime) {
    new Chart(timeCtx, {
      type: 'line',
      data: {
        labels: chartData.costsOverTime.map(d => d.date),
        datasets: [{
          label: 'Daily Cost ($)',
          data: chartData.costsOverTime.map(d => d.cost),
          borderColor: 'rgb(13, 110, 253)',
          backgroundColor: 'rgba(13, 110, 253, 0.1)',
          fill: true,
          tension: 0.3
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: function(value) {
                return '$' + value.toFixed(4);
              }
            }
          }
        }
      }
    });
  }

  // Provider Pie Chart
  const providerCtx = document.getElementById('providerChart');
  if (providerCtx && chartData.costsByProvider) {
    if (chartData.costsByProvider.length > 0) {
      new Chart(providerCtx, {
        type: 'doughnut',
        data: {
          labels: chartData.costsByProvider.map(d => d.provider),
          datasets: [{
            data: chartData.costsByProvider.map(d => d.cost),
            backgroundColor: [
              'rgb(13, 110, 253)',
              'rgb(25, 135, 84)',
            ],
            borderWidth: 0
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: 'bottom'
            },
            tooltip: {
              callbacks: {
                label: function(context) {
                  return context.label + ': $' + context.raw.toFixed(4);
                }
              }
            }
          }
        }
      });
    } else {
      providerCtx.parentElement.innerHTML = '<p class="text-muted text-center">No provider data available</p>';
    }
  }
});

})();
