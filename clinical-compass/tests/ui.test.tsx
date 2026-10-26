import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import { SearchField, Modal } from '../src/components/ui';
test('search exposes an accessible clear action',()=>{const change=vi.fn();render(<SearchField value="Анна" onChange={change}/>);fireEvent.click(screen.getByRole('button',{name:'Очистить поиск'}));expect(change).toHaveBeenCalledWith('');});
test('dialog supports Escape and restores scroll state',()=>{const close=vi.fn();const {unmount}=render(<Modal title="Проверка" onClose={close}><button>Действие</button></Modal>);expect(screen.getByRole('dialog',{name:'Проверка'})).toHaveFocus();fireEvent.keyDown(document,{key:'Escape'});expect(close).toHaveBeenCalledOnce();unmount();expect(document.body.style.overflow).toBe('');});
