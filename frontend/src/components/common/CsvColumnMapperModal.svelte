<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export let show = false;
  export let columns: string[] = [];

  const dispatch = createEventDispatcher();

  let currentStep = 1;
  let selectedColumns: { [key: string]: string } = {
    col_company: '',
    col_street: '',
    col_house_number: '',
    col_city: ''
  };

  const steps = [
    { step: 1, title: 'Business Name', key: 'col_company' },
    { step: 2, title: 'Street Name', key: 'col_street' },
    { step: 3, title: 'House Number', key: 'col_house_number' },
    { step: 4, title: 'Place / City', key: 'col_city' }
  ];

  $: currentStepData = steps[currentStep - 1];
  $: canProceed = selectedColumns[currentStepData.key] !== '';
  $: isLastStep = currentStep === steps.length;

  function handleNext() {
    if (currentStep < steps.length) {
      currentStep++;
    } else {
      handleComplete();
    }
  }

  function handleBack() {
    if (currentStep > 1) {
      currentStep--;
    }
  }

  function handleComplete() {
    dispatch('complete', selectedColumns);
    resetAndClose();
  }

  function handleClose() {
    dispatch('cancel');
    resetAndClose();
  }

  function resetAndClose() {
    show = false;
    currentStep = 1;
    selectedColumns = {
      col_company: '',
      col_street: '',
      col_house_number: '',
      col_city: ''
    } as { [key: string]: string };
  }
</script>

{#if show}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-noninteractive-element-interactions -->
  <div class="overlay" on:click={handleClose} role="dialog" aria-modal="true" tabindex="-1">
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
    <div class="modal" on:click|stopPropagation role="document">
      <button class="close" on:click={handleClose} aria-label="Close">×</button>

      <h2>Map CSV Columns</h2>
      
      <div class="steps">
        {#each steps as step}
          <div class="step" class:active={step.step <= currentStep}>
            <span>{step.step}</span>
          </div>
          {#if step.step < steps.length}
            <div class="line" class:active={step.step < currentStep}></div>
          {/if}
        {/each}
      </div>

      <h3>{currentStepData.title}</h3>

      <select bind:value={selectedColumns[currentStepData.key]}>
        <option value="">Choose column</option>
        {#each columns as column}
          <option value={column}>{column}</option>
        {/each}
      </select>

      <div class="buttons">
        <button class="btn-back" on:click={currentStep > 1 ? handleBack : handleClose}>
          {currentStep > 1 ? 'Back' : 'Cancel'}
        </button>
        <button class="btn-next" on:click={handleNext} disabled={!canProceed}>
          {isLastStep ? 'Complete' : 'Next'} →
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    background: white;
    border-radius: 8px;
    width: 90%;
    max-width: 480px;
    padding: 24px;
    position: relative;
  }

  .close {
    position: absolute;
    top: 12px;
    right: 12px;
    background: none;
    border: none;
    font-size: 28px;
    color: #999;
    cursor: pointer;
    line-height: 1;
    padding: 0;
    width: 24px;
    height: 24px;
  }

  .close:hover {
    color: #333;
  }

  h2 {
    font-size: 20px;
    font-weight: 600;
    margin: 0 0 20px;
    text-align: center;
    color: #1a1a1a;
  }

  .steps {
    display: flex;
    justify-content: center;
    align-items: center;
    margin-bottom: 24px;
  }

  .step {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: #e5e5e5;
    color: #999;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    font-size: 14px;
  }

  .step.active {
    background: #2563eb;
    color: white;
  }

  .line {
    width: 40px;
    height: 2px;
    background: #e5e5e5;
  }

  .line.active {
    background: #2563eb;
  }

  h3 {
    font-size: 16px;
    font-weight: 600;
    margin: 0 0 12px;
    text-align: center;
    color: #333;
  }

  select {
    width: 100%;
    padding: 10px 12px;
    font-size: 14px;
    border: 2px solid #e5e5e5;
    border-radius: 6px;
    background: white;
    cursor: pointer;
    margin-bottom: 20px;
  }

  select:focus {
    outline: none;
    border-color: #2563eb;
  }

  .buttons {
    display: flex;
    gap: 8px;
  }

  .btn-back,
  .btn-next {
    flex: 1;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: 500;
    border-radius: 6px;
    border: none;
    cursor: pointer;
  }

  .btn-back {
    background: #f1f5f9;
    color: #475569;
  }

  .btn-back:hover {
    background: #e2e8f0;
  }

  .btn-next {
    background: #2563eb;
    color: white;
  }

  .btn-next:hover {
    background: #1d4ed8;
  }

  .btn-next:disabled {
    background: #cbd5e1;
    cursor: not-allowed;
  }
</style>
