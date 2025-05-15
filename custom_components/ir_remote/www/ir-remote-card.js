class IRRemoteCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
  }

  setConfig(config) {
    if (!config) {
      throw new Error("Не указана конфигурация");
    }
    
    this.config = config;
    this.devices = ['none'];
    this.commands = {};
    this.selectedDevice = 'none';
    this.selectedCommand = 'none';
    this.buttonName = '';
    this.newDeviceName = '';
    
    this.render();
    this.loadData();
  }
  
  async loadData() {
    try {
      // Получаем данные из ir_codes.json через специальный сервис
      const result = await this._hass.callService('ir_remote', 'get_data', {});
      
      if (result && result.devices) {
        this.devices = ['none', ...result.devices];
        this.commands = result.commands || {};
        
        // Обновляем селекторы устройств
        const sendDeviceSelect = this.shadowRoot.getElementById('send-device');
        const learnDeviceSelect = this.shadowRoot.getElementById('learn-device');
        
        if (sendDeviceSelect) {
          sendDeviceSelect.innerHTML = this.devices.map(
            device => `<option value="${device}">${device}</option>`
          ).join('');
        }
        
        if (learnDeviceSelect) {
          learnDeviceSelect.innerHTML = this.devices.map(
            device => `<option value="${device}">${device}</option>`
          ).join('');
        }
        
        // Обновляем селектор команд
        this.updateCommandSelect();
      }
    } catch (error) {
      console.error('Ошибка загрузки данных:', error);
      // Показываем ошибку пользователю
      this.showNotification('Ошибка загрузки данных: ' + error.message, 'error');
    }
  }
  
  updateCommandSelect() {
    const commandSelect = this.shadowRoot.getElementById('command-select');
    if (!commandSelect) return;
    
    if (this.selectedDevice && this.selectedDevice !== 'none' && 
        this.commands && this.commands[this.selectedDevice]) {
      
      const deviceCommands = ['none', ...this.commands[this.selectedDevice]];
      commandSelect.innerHTML = deviceCommands.map(
        cmd => `<option value="${cmd}">${cmd}</option>`
      ).join('');
    } else {
      commandSelect.innerHTML = '<option value="none">Выберите команду</option>';
    }
  }
  
  async handleSendCommand() {
    if (this.selectedDevice === 'none' || this.selectedCommand === 'none') {
      this.showNotification('Выберите устройство и команду', 'warning');
      return;
    }
    
    try {
      await this._hass.callService('ir_remote', 'send_command', {
        device: this.selectedDevice,
        command: this.selectedCommand
      });
      
      this.showNotification(`Команда ${this.selectedCommand} отправлена на устройство ${this.selectedDevice}`, 'success');
    } catch (error) {
      console.error('Ошибка отправки команды:', error);
      this.showNotification('Ошибка отправки команды: ' + error.message, 'error');
    }
  }
  
  async handleLearnCode() {
    if (this.selectedLearnDevice === 'none' || !this.buttonName.trim()) {
      this.showNotification('Выберите устройство и введите название кнопки', 'warning');
      return;
    }
    
    try {
      await this._hass.callService('ir_remote', 'learn_code', {
        device: this.selectedLearnDevice,
        button: this.buttonName.trim()
      });
      
      this.showNotification(`Обучение началось для кнопки ${this.buttonName} на устройстве ${this.selectedLearnDevice}. Направьте пульт на приемник и нажмите нужную кнопку`, 'info');
    } catch (error) {
      console.error('Ошибка запуска обучения:', error);
      this.showNotification('Ошибка запуска обучения: ' + error.message, 'error');
    }
  }
  
  async handleAddDevice() {
    if (!this.newDeviceName.trim()) {
      this.showNotification('Введите название устройства', 'warning');
      return;
    }
    
    try {
      const response = await this._hass.callService('ir_remote', 'add_device', {
        name: this.newDeviceName.trim()
      });
      
      this.showNotification(`Устройство ${this.newDeviceName} успешно добавлено`, 'success');
      
      // Очищаем поле ввода
      const newDeviceInput = this.shadowRoot.getElementById('new-device-input');
      if (newDeviceInput) {
        newDeviceInput.value = '';
        this.newDeviceName = '';
      }
      
      // Перезагружаем данные
      this.loadData();
    } catch (error) {
      console.error('Ошибка добавления устройства:', error);
      this.showNotification('Ошибка добавления устройства: ' + error.message, 'error');
    }
  }
  
  showNotification(message, type = 'info') {
    const event = new CustomEvent('hass-notification', {
      detail: { message, type, duration: 3000 }
    });
    window.dispatchEvent(event);
  }
  
  connectedCallback() {
    this.render();
    
    // Добавляем обработчики событий
    const sendDeviceSelect = this.shadowRoot.getElementById('send-device');
    if (sendDeviceSelect) {
      sendDeviceSelect.addEventListener('change', (e) => {
        this.selectedDevice = e.target.value;
        this.updateCommandSelect();
      });
    }
    
    const commandSelect = this.shadowRoot.getElementById('command-select');
    if (commandSelect) {
      commandSelect.addEventListener('change', (e) => {
        this.selectedCommand = e.target.value;
      });
    }
    
    const learnDeviceSelect = this.shadowRoot.getElementById('learn-device');
    if (learnDeviceSelect) {
      learnDeviceSelect.addEventListener('change', (e) => {
        this.selectedLearnDevice = e.target.value;
      });
    }
    
    const buttonNameInput = this.shadowRoot.getElementById('button-name-input');
    if (buttonNameInput) {
      buttonNameInput.addEventListener('input', (e) => {
        this.buttonName = e.target.value;
      });
    }
    
    const newDeviceInput = this.shadowRoot.getElementById('new-device-input');
    if (newDeviceInput) {
      newDeviceInput.addEventListener('input', (e) => {
        this.newDeviceName = e.target.value;
      });
    }
    
    const sendButton = this.shadowRoot.getElementById('send-button');
    if (sendButton) {
      sendButton.addEventListener('click', () => this.handleSendCommand());
    }
    
    const learnButton = this.shadowRoot.getElementById('learn-button');
    if (learnButton) {
      learnButton.addEventListener('click', () => this.handleLearnCode());
    }
    
    const addDeviceButton = this.shadowRoot.getElementById('add-device-button');
    if (addDeviceButton) {
      addDeviceButton.addEventListener('click', () => this.handleAddDevice());
    }
  }
  
  set hass(hass) {
    this._hass = hass;
    
    // Загружаем данные при первой установке hass
    if (!this.initialDataLoaded) {
      this.loadData();
      this.initialDataLoaded = true;
    }
  }
  
  render() {
    if (!this.shadowRoot) return;
    
    this.shadowRoot.innerHTML = `
      <ha-card header="ИК-пульт">
        <div class="card-content">
          <div class="section">
            <h3>Отправка команд</h3>
            <div class="row">
              <label for="send-device">Устройство:</label>
              <select id="send-device">
                <option value="none">Выберите устройство</option>
                ${this.devices.map(device => `<option value="${device}">${device}</option>`).join('')}
              </select>
            </div>
            <div class="row">
              <label for="command-select">Команда:</label>
              <select id="command-select">
                <option value="none">Выберите команду</option>
              </select>
            </div>
            <div class="row">
              <button id="send-button" class="primary">Отправить команду</button>
            </div>
          </div>
          
          <div class="section">
            <h3>Обучение новым командам</h3>
            <div class="row">
              <label for="learn-device">Устройство:</label>
              <select id="learn-device">
                <option value="none">Выберите устройство</option>
                ${this.devices.map(device => `<option value="${device}">${device}</option>`).join('')}
              </select>
            </div>
            <div class="row">
              <label for="button-name-input">Название кнопки:</label>
              <input type="text" id="button-name-input" placeholder="Введите название кнопки">
            </div>
            <div class="row">
              <button id="learn-button" class="warning">Начать обучение</button>
            </div>
          </div>
          
          <div class="section">
            <h3>Добавление устройств</h3>
            <div class="row">
              <label for="new-device-input">Название устройства:</label>
              <input type="text" id="new-device-input" placeholder="Введите название нового устройства">
            </div>
            <div class="row">
              <button id="add-device-button" class="success">Добавить устройство</button>
            </div>
          </div>
        </div>
      </ha-card>
      
      <style>
        ha-card {
          max-width: 100%;
          margin: 0 auto;
        }
        .card-content {
          padding: 16px;
        }
        .section {
          margin-bottom: 24px;
          padding-bottom: 16px;
          border-bottom: 1px solid #eee;
        }
        .section:last-child {
          border-bottom: none;
          margin-bottom: 0;
        }
        h3 {
          margin-top: 0;
          margin-bottom: 16px;
          color: var(--primary-text-color);
          font-size: 18px;
        }
        .row {
          display: flex;
          flex-direction: row;
          align-items: center;
          margin-bottom: 8px;
        }
        label {
          flex: 0 0 140px;
          font-weight: 500;
        }
        select, input {
          flex: 1;
          padding: 8px;
          border-radius: 4px;
          border: 1px solid #ccc;
          background-color: var(--card-background-color, white);
          color: var(--primary-text-color);
        }
        button {
          cursor: pointer;
          padding: 8px 16px;
          border: none;
          border-radius: 4px;
          margin-top: 8px;
          color: white;
          font-weight: 500;
          width: 100%;
        }
        .primary {
          background-color: var(--primary-color, #03a9f4);
        }
        .warning {
          background-color: var(--warning-color, #ff9800);
        }
        .success {
          background-color: var(--success-color, #4caf50);
        }
        @media (max-width: 600px) {
          .row {
            flex-direction: column;
            align-items: stretch;
          }
          label {
            margin-bottom: 4px;
          }
        }
      </style>
    `;
  }
}

customElements.define('ir-remote-card', IRRemoteCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'ir-remote-card',
  name: 'ИК-пульт',
  description: 'Карточка для управления ИК-пультом'
});